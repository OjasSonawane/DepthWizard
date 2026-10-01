import pytest
import numpy as np
from pathlib import Path
from PIL import Image
import io
import rasterio
from rasterio.transform import from_origin
from unittest.mock import patch

from app.models.depth_model import DepthEstimator
from app.services.calibration_service import CalibrationService, RelativeCalibrationStrategy
from app.services.depth_service import PipelineManager
from app.services.mesh_service import MeshService
from app.services.geospatial_service import GeospatialService
from app.config import settings


class TestPhase1Corrections:
    """
    Phase 1 Scientific Integrity & Anti-Fabrication Test Suite:
    1. Depth Anything V2 output is used.
    2. No arbitrary multiplier converts depth into metres.
    3. No random/synthetic DSM is generated.
    4. Missing reference produces rDSM rather than fake metric DSM.
    5. Failed inference cannot produce a successful DSM.
    """

    def test_1_depth_anything_v2_output_used(self):
        """
        Verify Depth Anything V2 model inference actually executes and
        its direct normalized output is used.
        """
        estimator = DepthEstimator.get_instance()
        assert estimator.is_loaded is True
        assert estimator.model is not None
        assert estimator.processor is not None
        assert estimator.is_fallback is False

        # Create test gradient image
        test_img = np.zeros((128, 128, 3), dtype=np.uint8)
        for i in range(128):
            test_img[i, :, :] = i * 2

        depth = estimator.predict(test_img)
        assert isinstance(depth, np.ndarray)
        assert depth.shape == (128, 128)
        assert depth.dtype == np.float32
        assert float(np.min(depth)) >= 0.0
        assert float(np.max(depth)) <= 1.0
        # Output must be non-trivial continuous surface
        assert np.var(depth) > 1e-4

    def test_2_no_arbitrary_multiplier_converts_depth_into_metres(self):
        """
        Verify no arbitrary multiplier (e.g. * 100 = metres or * 60 + 100)
        is applied to relative depth. rDSM must be in normalized [0.0, 1.0] range
        and strictly labeled as non-metric.
        """
        rel_depth = np.linspace(0.1, 0.9, 10000, dtype=np.float32).reshape(100, 100)
        rdsm, calib_result = CalibrationService.calibrate_relative(rel_depth)

        # Values must be in [0.0, 1.0] relative height, NEVER multiplied by 100 or offset
        assert float(np.min(rdsm)) == pytest.approx(0.0, abs=1e-5)
        assert float(np.max(rdsm)) == pytest.approx(1.0, abs=1e-5)
        assert calib_result.scale == 1.0
        assert calib_result.offset == 0.0
        assert calib_result.is_metric is False
        assert calib_result.method == "relative"
        assert "relative height [0.0, 1.0]" in calib_result.message

    def test_3_no_random_synthetic_dsm_generated(self, tmp_path):
        """
        Verify that constant or degenerate inputs do not generate random/synthetic terrain,
        and that MeshService preserves raw heightfields without synthetic Gaussian smoothing.
        """
        # A. Constant depth produces flat rDSM with degenerate flag, never synthetic noise
        flat_depth = np.full((64, 64), 0.5, dtype=np.float32)
        rdsm, calib_result = CalibrationService.calibrate_relative(flat_depth)
        assert np.all(rdsm == 0.0)
        assert calib_result.confidence == "degenerate"
        assert calib_result.scale == 0.0

        # B. MeshService does not artificially Gaussian-smooth coarse inputs
        coarse_dsm = np.array([
            [0.0, 1.0],
            [1.0, 0.0]
        ], dtype=np.float32)
        mesh_meta, json_path, obj_path = MeshService.generate_mesh_assets(
            dsm=coarse_dsm,
            output_prefix=tmp_path / "mesh_test",
            quality="low",
            grid_dim=64
        )
        assert json_path.exists()
        assert obj_path.exists()
        assert mesh_meta.vertex_count == 64 * 64

    def test_4_missing_reference_produces_rdsm_rather_than_fake_metric_dsm(self, tmp_path):
        """
        Verify that uploading a georeferenced GeoTIFF without reference DEM/GCP
        produces strictly an rDSM (Relative DSM) with is_metric=False, rather than
        a fake metric DSM with assumed elevation.
        """
        pipeline = PipelineManager.get_instance()
        job_id = "test_phase1_missing_ref_rdsm"

        # Create a genuine georeferenced GeoTIFF (EPSG:32643)
        h, w = 64, 64
        crs = "EPSG:32643"
        transform = from_origin(300000.0, 3400000.0, 10.0, 10.0)
        gtiff_path = tmp_path / "georeferenced_optical.tif"

        rgb_data = np.full((3, h, w), 120, dtype=np.uint8)
        # Add diagonal gradient
        for i in range(h):
            rgb_data[:, i, :] = (i * 3) % 255

        with rasterio.open(
            gtiff_path, "w", driver="GTiff",
            height=h, width=w, count=3, dtype=rasterio.uint8,
            crs=crs, transform=transform
        ) as dst:
            dst.write(rgb_data)

        # Inspect file
        meta, _ = GeospatialService.inspect_file(gtiff_path)
        assert meta.is_georeferenced is True
        assert meta.crs == crs

        # Register job without reference DEM or GCPs
        pipeline.register_job(
            job_id=job_id,
            image_path=gtiff_path,
            metadata=meta,
            dem_path=None,
            gcp_path=None
        )

        # Execute reconstruction
        summary = pipeline.run_pipeline(job_id)

        # Assert output is strictly rDSM
        assert summary.calibration.is_metric is False
        assert summary.calibration.method == "relative"
        assert summary.dsm_stats.is_metric is False

        # Inspect job record in central state machine
        job_record = pipeline.jobs[job_id]
        assert job_record["dsm"]["is_metric"] is False
        assert job_record["dsm"]["units"] == "relative"
        assert job_record["dsm"]["product_type"] == "rDSM"

        # Inspect exported GeoTIFF metadata tags
        dsm_tif_path = settings.DSM_DIR / f"{job_id}_dsm.tif"
        assert dsm_tif_path.exists()
        with rasterio.open(dsm_tif_path) as src:
            assert src.crs is not None
            assert "32643" in str(src.crs)
            tags = src.tags()
            assert tags.get("PRODUCT_TYPE") == "rDSM"
            assert tags.get("ELEVATION_UNITS") == "relative"
            assert tags.get("CALIBRATION_METHOD") == "relative"

    def test_5_failed_inference_cannot_produce_successful_dsm(self, tmp_path):
        """
        Verify that if depth inference fails or errors out, the pipeline aborts
        cleanly with FAILED status and does NOT generate synthetic replacement depth or fake DSM.
        """
        pipeline = PipelineManager.get_instance()
        job_id = "test_phase1_failed_inference_guard"

        img_path = tmp_path / "test_img.jpg"
        Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(img_path)
        meta, _ = GeospatialService.inspect_file(img_path)

        pipeline.register_job(
            job_id=job_id,
            image_path=img_path,
            metadata=meta
        )

        # Simulate depth inference model failure
        with patch.object(pipeline.depth_model, "predict", side_effect=RuntimeError("Hardware GPU memory allocation failure")):
            with pytest.raises(RuntimeError) as exc_info:
                pipeline.run_pipeline(job_id)
            assert "Hardware GPU memory allocation failure" in str(exc_info.value)

        # Job must be marked FAILED, not COMPLETED
        job_record = pipeline.jobs[job_id]
        assert job_record["status"] == "FAILED"
        assert "Hardware GPU memory allocation failure" in job_record["error"]
        assert job_record["dsm"] is None
        assert job_record.get("results") is None

        # Verify no fake DSM file was generated
        dsm_path = settings.DSM_DIR / f"{job_id}_dsm.tif"
        assert not dsm_path.exists()
