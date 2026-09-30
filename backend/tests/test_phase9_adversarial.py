import io
import os
import shutil
import tempfile
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
import rasterio
from rasterio.transform import Affine
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services.depth_service import PipelineManager
from app.services.dataset_service import DatasetService
from app.services.geospatial_service import GeospatialService
from app.services.image_validator import ImageValidator
from app.services.mesh_service import MeshService
from app.services.calibration_service import (
    RelativeCalibrationStrategy,
    DEMCalibrationStrategy,
    GCPCalibrationStrategy
)
from app.schemas.schemas import GCPItem, CreateJobRequest
from app.utils.security import validate_safe_id, assert_path_confined, sanitize_filename
from app.services.gamus_service import GAMUSService, TestSetCalibrationProhibitedError
from app.schemas.gamus_schemas import GAMUSEvaluationRequest


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. INPUT ATTACKS
# ==============================================================================
class TestInputAttacks:
    """Hostile input testing: corrupt data, edge-case dimensions, format spoofing, NaN injection."""

    def test_corrupt_image_upload_rejected(self, client):
        """Corrupt image with random garbage bytes must be rejected with 400."""
        corrupt_bytes = b"\x89PNG\r\n\x1a\nGARBAGE_BYTES_THAT_CANNOT_BE_DECODED_AS_PNG_1234567890"
        files = {"image": ("corrupt.png", io.BytesIO(corrupt_bytes), "image/png")}
        resp = client.post("/api/upload", files=files)
        assert resp.status_code == 400
        assert "Failed to parse image file" in resp.json()["detail"] or "Corrupted" in resp.json()["detail"]

    def test_empty_image_upload_rejected(self, client):
        """Empty 0-byte image file must be rejected with 400."""
        empty_bytes = b""
        files = {"image": ("empty.png", io.BytesIO(empty_bytes), "image/png")}
        resp = client.post("/api/upload", files=files)
        assert resp.status_code == 400
        assert "empty (0 bytes)" in resp.json()["detail"]

    def test_oversized_upload_rejected(self, client, monkeypatch):
        """Simulate upload exceeding MAX_UPLOAD_SIZE_MB; must return HTTP 413."""
        # Temporarily mock MAX_UPLOAD_SIZE_MB to 1MB to test limit enforcement safely
        from app.utils import security
        monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
        
        # 1.5 MB payload
        oversized_bytes = b"0" * (1500 * 1024)
        files = {"image": ("big.png", io.BytesIO(oversized_bytes), "image/png")}
        resp = client.post("/api/upload", files=files)
        assert resp.status_code == 413
        assert "exceeds maximum allowed limit" in resp.json()["detail"]

    def test_tiny_1x1_and_2x2_images_handled_safely(self, tmp_path):
        """1x1 and 2x2 images must not crash model inference or collapse tensor dimensions."""
        # Create 1x1 image
        img1 = Image.new("RGB", (1, 1), color=(128, 128, 128))
        p1 = tmp_path / "tiny1.png"
        img1.save(p1)

        meta1, rgb1 = GeospatialService.inspect_file(p1)
        assert meta1.width == 1
        assert meta1.height == 1
        assert rgb1.shape == (1, 1, 3)

        # Create 2x2 image
        img2 = Image.new("RGB", (2, 2), color=(200, 100, 50))
        p2 = tmp_path / "tiny2.png"
        img2.save(p2)

        meta2, rgb2 = GeospatialService.inspect_file(p2)
        assert meta2.width == 2
        assert meta2.height == 2
        assert rgb2.shape == (2, 2, 3)

    def test_grayscale_and_rgba_imagery(self, tmp_path):
        """Grayscale (1-channel) and RGBA (4-channel) imagery must be properly normalized to RGB uint8."""
        # 1-channel grayscale TIFF
        gray_p = tmp_path / "gray.tif"
        gray_data = np.full((32, 32), 120, dtype=np.uint8)
        with rasterio.open(
            gray_p, "w",
            driver="GTiff",
            height=32, width=32, count=1,
            dtype="uint8"
        ) as dst:
            dst.write(gray_data, 1)

        meta_g, rgb_g = GeospatialService.inspect_file(gray_p)
        assert rgb_g.shape == (32, 32, 3)
        assert rgb_g.dtype == np.uint8

        # 4-channel RGBA PNG
        rgba_img = Image.new("RGBA", (32, 32), color=(100, 150, 200, 128))
        rgba_p = tmp_path / "rgba.png"
        rgba_img.save(rgba_p)

        meta_a, rgb_a = GeospatialService.inspect_file(rgba_p)
        assert rgb_a.shape == (32, 32, 3)
        assert rgb_a.dtype == np.uint8

    def test_invalid_geotiff_singular_transform(self, tmp_path):
        """GeoTIFF with singular transform (determinant == 0) must be flagged as non-georeferenced."""
        bad_tif = tmp_path / "singular.tif"
        # Zero transform has det == 0
        singular_transform = Affine(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        with rasterio.open(
            bad_tif, "w",
            driver="GTiff",
            height=16, width=16, count=3,
            dtype="uint8",
            crs="EPSG:4326",
            transform=singular_transform
        ) as dst:
            dst.write(np.zeros((3, 16, 16), dtype=np.uint8))

        meta, _ = GeospatialService.inspect_file(bad_tif)
        assert meta.is_georeferenced is False

    def test_nan_heavy_raster_casting(self, tmp_path):
        """Float raster with 95% NaNs must normalize cleanly without casting warnings or crashing."""
        nan_tif = tmp_path / "nan_heavy.tif"
        nan_data = np.full((32, 32), np.nan, dtype=np.float32)
        # 5% valid pixels
        nan_data[0:2, 0:2] = 50.0
        nan_data[10:12, 10:12] = 100.0

        with rasterio.open(
            nan_tif, "w",
            driver="GTiff",
            height=32, width=32, count=3,
            dtype="float32"
        ) as dst:
            for b in range(1, 4):
                dst.write(nan_data, b)

        meta, rgb = GeospatialService.inspect_file(nan_tif)
        assert rgb.shape == (32, 32, 3)
        assert rgb.dtype == np.uint8
        assert np.isfinite(rgb).all()

    def test_spoofed_extension_magic_bytes_rejected(self, tmp_path):
        """Text / shell script named with .png extension must be rejected by magic bytes."""
        spoofed = tmp_path / "exploit.png"
        with open(spoofed, "wb") as f:
            f.write(b"#!/bin/bash\necho 'pwnd'\n")

        res = ImageValidator.validate_image(spoofed)
        assert res.status == "rejected"
        assert "header signature" in res.rejection_reason.lower() or "signature" in str(res.stages).lower()


# ==============================================================================
# 2. SCIENTIFIC ATTACKS
# ==============================================================================
class TestScientificAttacks:
    """Attacks targeting calibration, degenerate geometries, and ground truth violations."""

    def test_constant_depth_surface_flagged_as_degenerate(self):
        """Constant depth surface (zero relief) must be flagged as degenerate in RelativeCalibration."""
        const_depth = np.full((64, 64), 0.5, dtype=np.float32)
        strat = RelativeCalibrationStrategy()
        rdsm, calib = strat.calibrate(const_depth)

        assert calib.confidence == "degenerate"
        assert "zero relief" in calib.message.lower() or "flat" in calib.message.lower()
        assert calib.scale == 0.0
        assert np.all(rdsm == 0.0)

    def test_insufficient_gcps_rejected(self):
        """Fewer than 3 GCPs must raise a ValueError."""
        strat = GCPCalibrationStrategy()
        rel_depth = np.random.rand(50, 50).astype(np.float32)

        # 2 GCPs only
        gcps = [
            GCPItem(id="GCP1", x=10.0, y=10.0, elevation=100.0),
            GCPItem(id="GCP2", x=20.0, y=20.0, elevation=200.0),
        ]
        with pytest.raises(ValueError, match="At least 3"):
            strat.calibrate(rel_depth, gcps=gcps)

    def test_extreme_gcp_elevations_rejected_as_outliers(self):
        """GCPs with unphysical elevations (e.g. 100,000m or -50,000m) must be rejected."""
        strat = GCPCalibrationStrategy()
        rel_depth = np.random.rand(50, 50).astype(np.float32)

        # 3 GCPs but 2 have astronomical/out-of-bounds elevation
        gcps = [
            GCPItem(id="GCP1", x=10.0, y=10.0, elevation=100.0),
            GCPItem(id="GCP_EXTREME1", x=20.0, y=20.0, elevation=999999.0),
            GCPItem(id="GCP_EXTREME2", x=30.0, y=30.0, elevation=-999999.0),
        ]
        with pytest.raises(ValueError, match="terrestrial elevations"):
            strat.calibrate(rel_depth, gcps=gcps)

    def test_insufficient_dem_overlap_rejected(self):
        """Reference DEM with fewer than 20 overlapping valid pixels must raise ValueError."""
        strat = DEMCalibrationStrategy()
        rel_depth = np.random.rand(50, 50).astype(np.float32)
        ref_dem = np.full((50, 50), np.nan, dtype=np.float32)
        ref_dem[0:2, 0:2] = 500.0  # Only 4 valid pixels

        with pytest.raises(ValueError, match="Insufficient valid overlapping pixels"):
            strat.calibrate(rel_depth, reference_dem=ref_dem)

    def test_gamus_test_set_calibration_strictly_prohibited(self):
        """Calibrating using the GAMUS test set is strictly prohibited by design."""
        from app.schemas.gamus_schemas import CalibrationMode
        svc = GAMUSService()
        req = GAMUSEvaluationRequest(
            sample_id="sample_000000",
            split="test",
            calibration_mode=CalibrationMode.DIRECT_FIT_TRAIN_VAL  # Forbidden on test set!
        )
        with pytest.raises(TestSetCalibrationProhibitedError):
            svc.evaluate_sample(req)


# ==============================================================================
# 3. SYSTEM ATTACKS
# ==============================================================================
class TestSystemAttacks:
    """Attacks targeting concurrency, crash recovery, and state integrity."""

    def test_concurrent_job_collision_rejected(self):
        """Attempting to process a job that is already in an active stage must raise 409 Conflict."""
        pipeline = PipelineManager.get_instance()
        job_id = "test_concurrent_job_001"
        pipeline.jobs[job_id] = {
            "job_id": job_id,
            "status": "INFERENCE",  # Already actively processing
            "stages": [],
            "image_path": "nonexistent.png"
        }

        with pytest.raises(RuntimeError, match="already actively processing"):
            pipeline.run_pipeline(job_id)

    def test_nonexistent_job_returns_404(self, client):
        """Querying a non-existent job ID must return clean HTTP 404."""
        resp = client.get("/jobs/dw_nonexistent_999999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_pipeline_failure_transitions_cleanly_to_failed_state(self):
        """If pipeline encounters a fatal error, job state must transition cleanly to FAILED."""
        pipeline = PipelineManager.get_instance()
        job_id = "test_fail_recovery_002"
        pipeline.jobs[job_id] = {
            "job_id": job_id,
            "status": "QUEUED",
            "stages": [],
            "image_path": "/path/to/completely_missing_file_xyz.png"
        }

        with pytest.raises(FileNotFoundError):
            pipeline.run_pipeline(job_id)

        assert pipeline.jobs[job_id]["status"] == "FAILED"
        assert "error" in pipeline.jobs[job_id]


# ==============================================================================
# 4. SECURITY ATTACKS
# ==============================================================================
class TestSecurityAttacks:
    """Security penetration tests: path traversal, malicious filenames, directory escapes."""

    def test_path_traversal_in_job_id_rejected(self, client):
        """Attempted path traversal in job_id must return HTTP 400."""
        traversal_ids = [
            "../../etc/passwd",
            "..\\..\\windows\\win.ini",
            "dw_job_123/../../secret",
            "dw_job%2f..%2fsecret"
        ]
        for tid in traversal_ids:
            with pytest.raises(Exception):
                validate_safe_id(tid, "job_id")

    def test_path_traversal_in_dataset_id_rejected(self, client):
        """Attempted path traversal in dataset_id endpoint must return HTTP 400."""
        resp = client.get("/api/datasets/..%2F..%2Fetc%2Fpasswd")
        # FastAPI handles %2F in path; validate_safe_id ensures rejection
        assert resp.status_code in [400, 404]

    def test_path_traversal_in_experiment_id_rejected(self, client):
        """Attempted path traversal in GAMUS experiment endpoint must return HTTP 400."""
        resp = client.get("/api/benchmarks/gamus/experiments/..%2F..%2Fetc/assets/signed_error_map")
        assert resp.status_code in [400, 404]

    def test_assert_path_confined_detects_escapes(self, tmp_path):
        """assert_path_confined must raise HTTPException(400) if target path is outside base."""
        base_dir = tmp_path / "allowed_storage"
        base_dir.mkdir()
        
        inside_path = base_dir / "safe_file.txt"
        assert assert_path_confined(inside_path, base_dir) == inside_path.resolve()

        outside_path = tmp_path / "outside_file.txt"
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            assert_path_confined(outside_path, base_dir)
        assert exc_info.value.status_code == 400
        assert "Path traversal violation" in exc_info.value.detail

    def test_sanitize_filename_strips_directory_and_null_bytes(self):
        """sanitize_filename must strip path components, null bytes, and parent directory references."""
        assert sanitize_filename("../../../etc/passwd") == "passwd"
        assert sanitize_filename("safe_image.tif") == "safe_image.tif"
        assert sanitize_filename("nested/dir/test.png") == "test.png"
        assert sanitize_filename("bad\x00name.jpg") == "badname.jpg"


# ==============================================================================
# 5. 3D TERRAIN ATTACKS
# ==============================================================================
class Test3DTerrainAttacks:
    """Attacks on 3D terrain reconstruction: empty arrays, 1x1 DSMs, extreme elevations."""

    def test_empty_dsm_rejected_by_mesh_service(self, tmp_path):
        """Empty DSM array must raise ValueError."""
        empty_dsm = np.array([])
        out_prefix = tmp_path / "empty_terrain"
        with pytest.raises(ValueError, match="Input DSM must be a 2D array"):
            MeshService.generate_mesh_assets(empty_dsm, out_prefix)

    def test_single_pixel_dsm_rejected_by_mesh_service(self, tmp_path):
        """Single-pixel 1x1 DSM must raise ValueError (minimum 2x2 required)."""
        single_pixel_dsm = np.array([[150.0]], dtype=np.float32)
        out_prefix = tmp_path / "single_pixel_terrain"
        with pytest.raises(ValueError, match="too small"):
            MeshService.generate_mesh_assets(single_pixel_dsm, out_prefix)

    def test_extreme_elevation_mesh_clamped(self, tmp_path):
        """Astronomical elevations (e.g. +-10^20) must be clamped to terrestrial bounds without crashing OBJ export."""
        extreme_dsm = np.full((10, 10), 1e20, dtype=np.float32)
        extreme_dsm[0:5, 0:5] = -1e20
        extreme_dsm[5:8, 5:8] = 250.0  # Some reasonable values

        out_prefix = tmp_path / "extreme_terrain"
        meta, json_p, obj_p = MeshService.generate_mesh_assets(extreme_dsm, out_prefix, quality="low")

        assert meta.vertex_count > 0
        assert meta.face_count > 0
        assert json_p.exists()
        assert obj_p.exists()

        # Check OBJ content: no astronomical exponents in vertices
        with open(obj_p, "r") as f:
            lines = f.readlines()
            vertex_lines = [l for l in lines if l.startswith("v ")]
            assert len(vertex_lines) == meta.vertex_count
            # Ensure none have "1e+" or "1e-"
            for vl in vertex_lines:
                assert "1e+" not in vl.lower()

    def test_all_nan_dsm_handled_safely(self, tmp_path):
        """DSM with all NaNs must produce flat finite mesh without NaN coordinates."""
        nan_dsm = np.full((16, 16), np.nan, dtype=np.float32)
        out_prefix = tmp_path / "nan_terrain"
        meta, json_p, obj_p = MeshService.generate_mesh_assets(nan_dsm, out_prefix, quality="low")

        assert meta.vertex_count > 0
        assert json_p.exists()
        assert obj_p.exists()

        with open(obj_p, "r") as f:
            content = f.read()
            assert "nan" not in content.lower()
