import io
import json
import pytest
from pathlib import Path
from PIL import Image
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services.dataset_service import DatasetService
from app.services.depth_service import PipelineManager

client = TestClient(app)

def create_dummy_png(width=64, height=64, color=(120, 150, 200)) -> bytes:
    arr = np.full((height, width, 3), color, dtype=np.uint8)
    # Add a gradient pattern
    for y in range(height):
        for x in range(width):
            arr[y, x, 0] = (x * 4) % 256
            arr[y, x, 1] = (y * 4) % 256
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def create_tiny_png(width=16, height=10) -> bytes:
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestDatasetWorkflow:
    def test_preloaded_datasets_catalog(self):
        """Verifies preloaded datasets are listed, accessible, and serve valid thumbnails/previews."""
        resp = client.get("/api/datasets")
        assert resp.status_code == 200
        data = resp.json()
        assert "datasets" in data
        datasets = data["datasets"]
        
        preloaded_ids = [d["id"] for d in datasets if d["source"] == "preloaded"]
        assert "himalayan_valley" in preloaded_ids
        assert "coastal_estuary" in preloaded_ids
        assert "aerial_urban_flood" in preloaded_ids

        # Test thumbnail endpoint for himalayan_valley
        t_resp = client.get("/api/datasets/himalayan_valley/thumbnail")
        assert t_resp.status_code == 200
        assert t_resp.headers["content-type"].startswith("image/jpeg")
        assert len(t_resp.content) > 500

        # Test preview endpoint for himalayan_valley
        p_resp = client.get("/api/datasets/himalayan_valley/preview")
        assert p_resp.status_code == 200
        assert p_resp.headers["content-type"].startswith("image/jpeg")
        assert len(p_resp.content) > 1000

    def test_upload_optical_dataset_persists(self):
        """Tests that uploading an optical image creates persistent files on disk and appears in the library."""
        png_bytes = create_dummy_png(64, 64)
        files = {"image": ("test_survey.png", png_bytes, "image/png")}

        resp = client.post("/api/datasets/upload", files=files)
        assert resp.status_code == 200
        ds = resp.json()
        ds_id = ds["id"]
        assert ds_id.startswith("dw_ds_")
        assert ds["source"] == "user_upload"
        assert ds["name"] == "test_survey.png"
        assert ds["width"] == 64
        assert ds["height"] == 64
        assert ds["georeferenced"] is False

        # Verify physical disk directory
        ds_dir = settings.DATASETS_DIR / ds_id
        assert ds_dir.exists()
        assert (ds_dir / "original.png").exists()
        assert (ds_dir / "thumbnail.jpg").exists()
        assert (ds_dir / "preview.jpg").exists()
        assert (ds_dir / "metadata.json").exists()

        # Check that it appears in GET /api/datasets
        list_resp = client.get("/api/datasets")
        assert list_resp.status_code == 200
        ids = [d["id"] for d in list_resp.json()["datasets"]]
        assert ds_id in ids

        # Clean up
        del_resp = client.delete(f"/api/datasets/{ds_id}")
        assert del_resp.status_code == 200
        assert not ds_dir.exists()

    def test_multiple_uploads_and_duplicate_names(self):
        """Tests uploading files with identical filenames creates distinct IDs and isolated folders."""
        png_1 = create_dummy_png(64, 64, color=(100, 100, 100))
        png_2 = create_dummy_png(64, 64, color=(200, 200, 200))

        r1 = client.post("/api/datasets/upload", files={"image": ("duplicate.png", png_1, "image/png")})
        r2 = client.post("/api/datasets/upload", files={"image": ("duplicate.png", png_2, "image/png")})

        assert r1.status_code == 200
        assert r2.status_code == 200
        id1 = r1.json()["id"]
        id2 = r2.json()["id"]

        assert id1 != id2
        assert (settings.DATASETS_DIR / id1).exists()
        assert (settings.DATASETS_DIR / id2).exists()

        # Clean up
        client.delete(f"/api/datasets/{id1}")
        client.delete(f"/api/datasets/{id2}")

    def test_preloaded_cannot_be_deleted(self):
        """Verifies preloaded benchmark datasets cannot be deleted."""
        resp = client.delete("/api/datasets/himalayan_valley")
        assert resp.status_code == 400
        assert "Preloaded" in resp.json()["detail"]

    def test_select_and_prepare_job(self):
        """Verifies selecting a dataset and preparing a reconstruction job."""
        # 1. Select dataset
        sel_resp = client.post("/api/datasets/himalayan_valley/select")
        assert sel_resp.status_code == 200
        assert sel_resp.json()["id"] == "himalayan_valley"

        # 2. Prepare job
        prep_resp = client.post("/api/datasets/himalayan_valley/prepare-job")
        assert prep_resp.status_code == 200
        job_data = prep_resp.json()
        job_id = job_data["job_id"]
        assert job_id.startswith("dw_job_")
        assert job_data["dataset_id"] == "himalayan_valley"

        # 3. Check status
        st_resp = client.get(f"/api/jobs/{job_id}")
        assert st_resp.status_code == 200
        assert st_resp.json()["job_id"] == job_id

    def test_process_dataset_reconstruction(self):
        """Tests full reconstruction execution linked to a dataset."""
        # Process coastal_estuary
        proc_resp = client.post("/api/reconstruction/process", json={"dataset_id": "coastal_estuary"})
        assert proc_resp.status_code == 200
        summary = proc_resp.json()
        assert summary["dataset_id"] == "coastal_estuary"
        assert summary["is_georeferenced"] is True

        # Check dataset record was updated with results
        ds_resp = client.get("/api/datasets/coastal_estuary")
        assert ds_resp.status_code == 200
        ds_data = ds_resp.json()
        assert ds_data["status"] == "completed"
        assert ds_data["active_job_id"] == summary["job_id"]
        assert ds_data["latest_results"] is not None

    def test_persistence_across_service_reboot(self):
        """Tests that datasets persist on disk and reload accurately after re-initialization."""
        png_bytes = create_dummy_png(64, 64)
        files = {"image": ("persist_test.png", png_bytes, "image/png")}
        r = client.post("/api/datasets/upload", files=files)
        assert r.status_code == 200
        ds_id = r.json()["id"]

        # Simulate service restart by reinitializing DatasetService
        svc = DatasetService.get_instance()
        svc.datasets.clear()
        svc.initialize()

        assert ds_id in svc.datasets
        restored = svc.get_dataset(ds_id)
        assert restored.name == "persist_test.png"
        assert restored.width == 64
        assert restored.source == "user_upload"

        # Clean up
        client.delete(f"/api/datasets/{ds_id}")

    def test_low_resolution_image_advisory(self):
        """Tests that a 16x10 image is properly flagged with an advisory in metadata."""
        tiny_bytes = create_tiny_png(16, 10)
        files = {"image": ("tiny_drone.png", tiny_bytes, "image/png")}
        r = client.post("/api/datasets/upload", files=files)
        assert r.status_code == 200
        ds = r.json()
        ds_id = ds["id"]

        assert ds["is_low_resolution"] is True
        assert ds["resolution_warning"] is not None
        assert "16×10" in ds["resolution_warning"] or "16x10" in ds["resolution_warning"]

        # Clean up
        client.delete(f"/api/datasets/{ds_id}")
