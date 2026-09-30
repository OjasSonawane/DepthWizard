import io
import pytest
from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.services.image_validator import ImageValidator

client = TestClient(app)

def create_synthetic_terrain_png(width=512, height=512) -> bytes:
    """Generates high-entropy natural terrain texture with green/brown tones."""
    np.random.seed(42)
    x = np.linspace(0, 10, width)
    y = np.linspace(0, 10, height)
    xx, yy = np.meshgrid(x, y)
    elevation = np.sin(xx) * np.cos(yy) + 0.5 * np.sin(2 * xx + yy)
    elevation = (elevation - elevation.min()) / (elevation.max() - elevation.min() + 1e-6)
    
    r = (elevation * 120 + 40 + np.random.normal(0, 5, (height, width))).clip(0, 255).astype(np.uint8)
    g = (elevation * 140 + 60 + np.random.normal(0, 5, (height, width))).clip(0, 255).astype(np.uint8)
    b = (elevation * 80 + 30 + np.random.normal(0, 5, (height, width))).clip(0, 255).astype(np.uint8)
    
    rgb = np.stack([r, g, b], axis=-1)
    img = Image.fromarray(rgb)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def create_document_screenshot_png(width=500, height=400) -> bytes:
    """Creates a white document with stark black text lines (code or document)."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    for y in range(20, height - 20, 15):
        draw.line([(30, y), (width - 40, y)], fill=(20, 20, 25), width=3)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def create_solid_blank_png(width=200, height=200) -> bytes:
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def create_tiny_png(width=32, height=32) -> bytes:
    img = Image.new("RGB", (width, height), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestImageValidator:
    def test_synthetic_terrain_accepted(self, tmp_path):
        """Natural high-entropy terrain imagery should be marked ready or warning (suitable)."""
        data = create_synthetic_terrain_png(256, 256)
        path = tmp_path / "terrain.png"
        path.write_bytes(data)
        
        result = ImageValidator.validate_image(path)
        assert result.status in ["ready", "warning"]
        assert result.is_suitable is True
        assert result.suitability_score >= 50
        assert len(result.stages) >= 6

    def test_document_screenshot_rejected(self, tmp_path):
        """Document/code screenshot should be detected and rejected."""
        data = create_document_screenshot_png()
        path = tmp_path / "doc.png"
        path.write_bytes(data)
        
        result = ImageValidator.validate_image(path)
        assert result.status == "rejected"
        assert result.is_suitable is False
        assert "document" in result.detected_content.lower() or "text" in result.rejection_reason.lower()

    def test_solid_blank_image_rejected(self, tmp_path):
        """Blank image with 0 variance should be rejected."""
        data = create_solid_blank_png()
        path = tmp_path / "blank.png"
        path.write_bytes(data)
        
        result = ImageValidator.validate_image(path)
        assert result.status == "rejected"
        assert "variance" in result.rejection_reason.lower() or "blank" in result.rejection_reason.lower()

    def test_tiny_image_guardrail(self, tmp_path):
        """Images < 32px must fail resolution guardrails with rejection."""
        data = create_tiny_png(16, 16)
        path = tmp_path / "tiny.png"
        path.write_bytes(data)
        
        result = ImageValidator.validate_image(path)
        assert result.status == "rejected"
        assert "resolution" in result.rejection_reason.lower() or result.width < 32

    def test_api_validate_endpoint(self):
        """Test POST /api/datasets/validate endpoint."""
        doc_bytes = create_document_screenshot_png()
        resp = client.post(
            "/api/datasets/validate",
            files={"image": ("code_screenshot.png", doc_bytes, "image/png")}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"
        assert data["is_suitable"] is False
        assert "rejection_reason" in data

    def test_api_reconstruction_blocks_rejected_dataset(self):
        """Verify that attempting to prepare a job for a rejected dataset raises an error."""
        doc_bytes = create_document_screenshot_png()
        resp = client.post(
            "/api/datasets/upload",
            files={"image": ("screenshot.png", doc_bytes, "image/png")}
        )
        assert resp.status_code == 200
        ds_data = resp.json()
        assert ds_data["status"] == "rejected"
        ds_id = ds_data["id"]

        # Preparing job should fail
        prep_resp = client.post(f"/api/datasets/{ds_id}/prepare-job")
        assert prep_resp.status_code in [400, 422, 500]

        # Process reconstruction should also fail
        proc_resp = client.post("/api/reconstruction/process", json={"dataset_id": ds_id})
        assert proc_resp.status_code in [400, 422]
