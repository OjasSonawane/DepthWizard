import io
import json
import pytest
import numpy as np
from PIL import Image
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services.depth_service import PipelineManager
from app.schemas.schemas import JobState

client = TestClient(app)


def create_synthetic_geotiff(path, width=64, height=64, crs_str="EPSG:32643"):
    transform = from_origin(500000.0, 1000000.0, 10.0, 10.0)
    data = np.random.randint(40, 220, size=(3, height, width), dtype=np.uint8)
    with rasterio.open(
        path,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=3,
        dtype='uint8',
        crs=crs_str,
        transform=transform
    ) as dst:
        dst.write(data)
    return path


def create_synthetic_dem(path, width=64, height=64, crs_str="EPSG:32643"):
    transform = from_origin(500000.0, 1000000.0, 10.0, 10.0)
    y, x = np.mgrid[0:height, 0:width]
    elev = 500.0 + x * 2.0 + y * 1.5 + np.sin(x / 5.0) * 10.0
    elev = elev.astype(np.float32)
    with rasterio.open(
        path,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=1,
        dtype='float32',
        crs=crs_str,
        transform=transform,
        nodata=-9999.0
    ) as dst:
        dst.write(elev, 1)
    return path


class TestPhase6Integration:
    """
    Phase 6: Backend -> Existing UI Integration Test Suite.
    Ensures unified central processing job model, single job_id traceability,
    stable REST APIs, and honest metric reporting.
    """

    def test_single_job_id_full_pipeline_flow(self, tmp_path):
        """
        Tests: upload -> backend -> inference -> calibration -> DSM -> validation -> frontend
        All referencing the exact same job_id.
        """
        # 1. Create synthetic optical GeoTIFF
        img_path = tmp_path / "mission_optical.tif"
        create_synthetic_geotiff(img_path, width=64, height=64)

        # 2. Upload through /api/upload
        with open(img_path, "rb") as f:
            upload_resp = client.post(
                "/api/upload",
                files={"image": ("mission_optical.tif", f, "image/tiff")}
            )
        assert upload_resp.status_code == 200
        upload_data = upload_resp.json()
        job_id = upload_data["job_id"]
        assert job_id.startswith("dw_")

        # 3. Check initial job status is QUEUED
        status_resp = client.get(f"/api/jobs/{job_id}")
        assert status_resp.status_code == 200
        job_status = status_resp.json()
        assert job_status["job_id"] == job_id
        assert job_status["status"] == "QUEUED"
        assert job_status["input"] is not None
        assert job_status["input"]["filename"] == "input.tif"
        assert job_status["input"]["is_georeferenced"] is True
        assert job_status["input"]["crs"] == "EPSG:32643"

        # 4. Start processing via /api/jobs/{job_id}/start (or /api/process/{job_id})
        start_resp = client.post(f"/api/jobs/{job_id}/start")
        assert start_resp.status_code == 200
        summary = start_resp.json()
        assert summary["job_id"] == job_id
        assert summary["is_georeferenced"] is True

        # 5. Check completed job status and central job model fields
        status_after = client.get(f"/api/jobs/{job_id}").json()
        assert status_after["job_id"] == job_id
        assert status_after["status"] == "COMPLETED"
        assert status_after["progress"] == 100
        assert status_after["input"]["width"] == 64
        assert status_after["input"]["height"] == 64
        assert status_after["depth"] is not None
        assert status_after["depth"]["unit"] == "relative"
        assert status_after["depth"]["normalized_range"] == [0.0, 1.0]
        assert status_after["calibration"] is not None
        assert status_after["calibration"]["method"] == "scaled_estimate"
        assert status_after["dsm"] is not None
        assert status_after["dsm"]["is_metric"] is False
        assert status_after["artifacts"] is not None
        assert "dsm_geotiff" in status_after["artifacts"]
        assert "rgb_texture" in status_after["artifacts"]

        # 6. Query depth result endpoint
        depth_resp = client.get(f"/api/results/{job_id}/depth")
        assert depth_resp.status_code == 200
        depth_data = depth_resp.json()
        assert depth_data["job_id"] == job_id
        assert depth_data["min_val"] == 0.0
        assert depth_data["max_val"] == 1.0
        assert depth_data["unit"] == "relative"
        assert "depth_color" in depth_data
        assert "depth_gray" in depth_data

        # 7. Query DSM result endpoint
        dsm_resp = client.get(f"/api/results/{job_id}/dsm")
        assert dsm_resp.status_code == 200
        dsm_data = dsm_resp.json()
        assert dsm_data["job_id"] == job_id
        assert dsm_data["is_metric"] is False
        assert dsm_data["crs"] == "EPSG:32643"
        assert "dsm_geotiff" in dsm_data
        assert "stats" in dsm_data

        # 8. Query Validation endpoint before reference DEM (honest empty state)
        val_resp = client.get(f"/api/results/{job_id}/validation")
        assert val_resp.status_code == 200
        val_data = val_resp.json()
        assert val_data["job_id"] == job_id
        assert val_data["has_evaluation"] is False
        assert val_data["metrics"] is None
        assert "unavailable" in val_data["disclaimer"].lower()

        # 9. Co-register with reference DEM and compute real validation metrics
        dem_path = tmp_path / "reference_dem.tif"
        create_synthetic_dem(dem_path, width=64, height=64)

        with open(dem_path, "rb") as f:
            eval_post_resp = client.post(
                f"/api/evaluate/{job_id}",
                files={"reference_file": ("reference_dem.tif", f, "image/tiff")}
            )
        assert eval_post_resp.status_code == 200
        eval_post_data = eval_post_resp.json()
        assert eval_post_data["job_id"] == job_id
        assert eval_post_data["has_evaluation"] is True
        assert eval_post_data["metrics"]["mae"] > 0.0
        assert eval_post_data["metrics"]["rmse"] > 0.0
        assert -1.0 <= eval_post_data["metrics"]["pearson_r"] <= 1.0

        # 10. Query validation endpoint after evaluation
        val_after_resp = client.get(f"/api/results/{job_id}/validation")
        assert val_after_resp.status_code == 200
        assert val_after_resp.json()["has_evaluation"] is True
        assert val_after_resp.json()["metrics"]["mae"] == eval_post_data["metrics"]["mae"]

        # 11. Query Artifacts endpoint
        art_resp = client.get(f"/api/results/{job_id}/artifacts")
        assert art_resp.status_code == 200
        art_data = art_resp.json()
        assert art_data["job_id"] == job_id
        assert "dsm_geotiff" in art_data["artifacts"]
        assert "depth_color" in art_data["artifacts"]
        assert "error_map" in art_data["artifacts"]

        # 12. Query Zip export endpoint
        export_resp = client.get(f"/api/results/{job_id}/export")
        assert export_resp.status_code == 200
        assert export_resp.headers["content-type"] == "application/zip"

    def test_non_georeferenced_honest_unavailable_standard(self, tmp_path):
        """
        Verifies that non-georeferenced imagery correctly reports CRS as None/Unavailable,
        generates relative rDSM, and maintains zero fake/mock coordinates.
        """
        png_path = tmp_path / "drone_photo.png"
        img = Image.new("RGB", (80, 80), color=(100, 150, 75))
        img.save(png_path)

        with open(png_path, "rb") as f:
            upload_resp = client.post(
                "/api/upload",
                files={"image": ("drone_photo.png", f, "image/png")}
            )
        assert upload_resp.status_code == 200
        job_id = upload_resp.json()["job_id"]

        status = client.get(f"/api/jobs/{job_id}").json()
        assert status["input"]["is_georeferenced"] is False
        assert status["input"]["crs"] is None

        # Execute
        client.post(f"/api/process/{job_id}")

        dsm_data = client.get(f"/api/results/{job_id}/dsm").json()
        assert dsm_data["is_metric"] is False
        assert dsm_data["crs"] is None
        assert "relative" in dsm_data["elevation_units"]

    def test_create_job_endpoint_and_lifecycle(self, tmp_path):
        """
        Verifies POST /api/jobs/create with initial QUEUED status.
        """
        img_path = tmp_path / "test_create.tif"
        create_synthetic_geotiff(img_path, width=48, height=48)

        create_resp = client.post(
            "/api/jobs/create",
            json={"image_path": str(img_path)}
        )
        assert create_resp.status_code == 200
        job_data = create_resp.json()
        job_id = job_data["job_id"]
        assert job_data["status"] == "QUEUED"
        assert job_data["progress"] == 0

        # Start job
        start_resp = client.post(f"/api/jobs/{job_id}/start")
        assert start_resp.status_code == 200
        summary = start_resp.json()
        assert summary["job_id"] == job_id

        # Verify final status
        final_status = client.get(f"/api/jobs/{job_id}").json()
        assert final_status["status"] == "COMPLETED"
        assert final_status["progress"] == 100

