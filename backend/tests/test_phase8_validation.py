import pytest
import numpy as np
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient

from app.main import app
from app.services.evaluation_service import EvaluationService
from app.services.depth_service import PipelineManager
from app.schemas.schemas import EvaluationMetrics, EvaluationResponse, LandscapeMetric

client = TestClient(app)

class TestPhase8ScientificValidation:
    """
    Phase 8 Verification Suite:
    - Primary Metrics: MAE, RMSE, Pearson Correlation (r)
    - Additional Metrics: Bias (MBE), Median AE, P90 (LE90), P95 (LE95), Max Error, Valid Pixel %
    - All 6 Visualizations: Predicted map, Reference map, Signed error map, Absolute error map, Scatter points, Error histogram
    - Pixel Inspection: predicted, reference, error (honest 'Unavailable' when unreferenced)
    - Scene Stratification: Independent calculation per category; zero fabrication of missing classes
    """

    def test_primary_and_additional_metrics_exact_math(self, tmp_path):
        """
        Verifies exact numerical computation of all 9 primary & additional metrics:
        MAE, RMSE, Correlation, Bias, Median AE, P90, P95, Max Error, Valid Pixel %.
        """
        # Create 10x10 deterministic synthetic raster (100 pixels)
        ref = np.linspace(100.0, 200.0, 100, dtype=np.float32).reshape(10, 10)
        
        # Pred has known residuals:
        # 60 pixels with +4.0m error
        # 40 pixels with -2.0m error
        pred = ref.copy()
        pred[:6, :] += 4.0
        pred[6:, :] -= 2.0

        out_prefix = tmp_path / "test_p8_math"

        (
            metrics,
            err_png,
            abs_png,
            pred_png,
            ref_png,
            hist,
            scatter,
            strata,
            active_metrics,
            prof_name
        ) = EvaluationService.evaluate_against_reference(
            predicted_dsm=pred,
            reference_dsm=ref,
            output_prefix=out_prefix,
            profile="terrain_comprehensive"
        )

        # 1. MAE = (60 * 4.0 + 40 * 2.0) / 100 = 320 / 100 = 3.20m
        assert pytest.approx(metrics.mae, 1e-2) == 3.20

        # 2. RMSE = sqrt((60 * 16.0 + 40 * 4.0) / 100) = sqrt(1120 / 100) = sqrt(11.2) ≈ 3.3466m
        assert pytest.approx(metrics.rmse, 1e-2) == 3.35

        # 3. Pearson Correlation (r): slope gradient is perfectly preserved, so r should be > 0.99
        assert metrics.pearson_r > 0.99

        # 4. Bias / MBE = (60 * 4.0 - 40 * 2.0) / 100 = 160 / 100 = +1.60m
        assert pytest.approx(metrics.mbe, 1e-2) == 1.60

        # 5. Median Absolute Error: 40 entries of 2.0 and 60 entries of 4.0 -> median is 4.0m
        assert pytest.approx(metrics.median_abs_error, 1e-2) == 4.00

        # 6. P90 Error (LE90): 90th percentile of absolute errors [2.0 (40%), 4.0 (60%)] -> 4.0m
        assert pytest.approx(metrics.le90, 1e-2) == 4.00

        # 7. P95 Error (LE95): 95th percentile of absolute errors -> 4.0m
        assert pytest.approx(metrics.le95, 1e-2) == 4.00

        # 8. Maximum Error: max(|errors|) = 4.0m
        assert pytest.approx(metrics.max_abs_error, 1e-2) == 4.00

        # 9. Valid Pixel %: 100 / 100 = 100.0%
        assert metrics.valid_pixel_pct == 100.0
        assert metrics.valid_pixel_count == 100

    def test_all_six_visualization_artifacts(self, tmp_path):
        """
        Verifies that all 6 required visualization artifacts are properly generated:
        1. Predicted height map
        2. Reference height map
        3. Signed error map
        4. Absolute error map
        5. Predicted vs reference scatter plot
        6. Error histogram
        """
        ref = np.arange(144, dtype=np.float32).reshape(12, 12) + 50.0
        pred = ref + np.sin(ref) * 5.0

        out_prefix = tmp_path / "test_p8_vis"

        (
            metrics,
            err_png,
            abs_png,
            pred_png,
            ref_png,
            hist,
            scatter,
            strata,
            active,
            prof
        ) = EvaluationService.evaluate_against_reference(
            predicted_dsm=pred,
            reference_dsm=ref,
            output_prefix=out_prefix
        )

        # 1. Predicted height map
        assert pred_png.exists()
        with Image.open(pred_png) as img:
            assert img.size == (12, 12)
            assert img.mode == "RGB"

        # 2. Reference height map
        assert ref_png.exists()
        with Image.open(ref_png) as img:
            assert img.size == (12, 12)
            assert img.mode == "RGB"

        # 3. Signed error map
        assert err_png.exists()
        with Image.open(err_png) as img:
            assert img.size == (12, 12)
            assert img.mode == "RGB"

        # 4. Absolute error map
        assert abs_png.exists()
        with Image.open(abs_png) as img:
            assert img.size == (12, 12)
            assert img.mode == "RGB"

        # 5. Scatter Plot points
        assert len(scatter) > 0
        assert len(scatter) <= 200
        for pt in scatter:
            assert "reference" in pt
            assert "predicted" in pt
            assert "error" in pt
            assert pytest.approx(pt["predicted"] - pt["reference"], 0.2) == pt["error"]

        # 6. Error Histogram
        assert len(hist) == 20
        total_counts = sum(b["count"] for b in hist)
        assert total_counts == 144
        total_pct = sum(b["percentage"] for b in hist)
        assert pytest.approx(total_pct, 1.0) == 100.0

    def test_pixel_inspection_interaction(self, tmp_path):
        """
        Verifies pixel inspection:
        - When reference data exists: queries pixel, returns predicted, reference, error
        - When reference data does not exist: returns reference=None, error=None (honest standard)
        """
        pipeline = PipelineManager.get_instance()
        job_id = "test_phase8_inspect_job"

        # Create synthetic DSM file
        dsm_arr = np.linspace(10.0, 50.0, 100, dtype=np.float32).reshape(10, 10)
        from app.config import settings
        dsm_dir = settings.STORAGE_DIR / "dsm"
        dsm_dir.mkdir(parents=True, exist_ok=True)
        np.save(dsm_dir / f"{job_id}_dsm.npy", dsm_arr)

        # Create synthetic Reference file
        ref_arr = dsm_arr + 2.5
        ref_path = tmp_path / f"{job_id}_ref.npy"
        np.save(ref_path, ref_arr)

        # Case A: Referenced Job
        pipeline.jobs[job_id] = {
            "status": "completed",
            "results": {
                "job_id": job_id,
                "filename": "test.tif",
                "is_georeferenced": False,
                "image_metadata": {
                    "width": 10, "height": 10, "format": "TIF", "file_size_bytes": 1000,
                    "is_georeferenced": False, "crs": None, "transform": None, "bounds": None, "resolution": None
                },
                "calibration": {
                    "method": "relative", "is_metric": True, "scale": 1.0, "offset": 0.0,
                    "confidence": "high", "message": "Standard calibrated"
                },
                "dsm_stats": {
                    "min_elevation": 10.0, "max_elevation": 50.0, "mean_elevation": 30.0, "median_elevation": 30.0,
                    "std_elevation": 10.0, "relief": 40.0, "average_slope_deg": 5.0, "max_slope_deg": 10.0,
                    "steep_area_pct": 0.0, "crs": None, "is_metric": True
                },
                "disaster_risk": {
                    "low_lying_area_pct": 0.0, "steep_slope_hazard_pct": 0.0, "moderate_slope_pct": 0.0,
                    "gentle_slope_pct": 100.0, "ruggedness_index": 0.0, "elevation_thresholds": {}
                },
                "timing_seconds": {"total": 1.0},
                "device_used": "cpu",
                "assets": {"dsm_geotiff": "", "dsm_color": "", "hillshade": "", "slope": "", "contour": "", "rgb_texture": ""},
                "dimensions": {
                    "input_width": 10, "input_height": 10, "depth_width": 10, "depth_height": 10,
                    "dsm_width": 10, "dsm_height": 10, "render_grid_width": 10, "render_grid_height": 10
                },
                "mesh_metadata": {
                    "grid_width": 10, "grid_height": 10, "vertex_count": 100, "face_count": 162,
                    "heightfield_url": "", "obj_url": "", "quality": "high"
                }
            },
            "ref_file_path": str(ref_path)
        }

        # Query pixel (x=4, y=5)
        resp = client.get(f"/api/results/{job_id}/inspect-point?pixel_x=4&pixel_y=5")
        assert resp.status_code == 200
        data = resp.json()

        assert data["pixel_coords"] == {"x": 4, "y": 5}
        expected_pred = float(dsm_arr[5, 4])
        expected_ref = float(ref_arr[5, 4])
        assert pytest.approx(data["predicted_height"], 0.05) == expected_pred
        assert pytest.approx(data["reference_height"], 0.05) == expected_ref
        assert pytest.approx(data["error"], 0.05) == round(expected_pred - expected_ref, 2)

        # Case B: Unreferenced Job (remove ref_file_path)
        unreferenced_id = "test_phase8_unref_job"
        pipeline.jobs[unreferenced_id] = {
            **pipeline.jobs[job_id],
            "ref_file_path": None
        }
        np.save(dsm_dir / f"{unreferenced_id}_dsm.npy", dsm_arr)

        resp_unref = client.get(f"/api/results/{unreferenced_id}/inspect-point?pixel_x=4&pixel_y=5")
        assert resp_unref.status_code == 200
        data_unref = resp_unref.json()
        assert data_unref["predicted_height"] == round(expected_pred, 2)
        assert data_unref["reference_height"] is None
        assert data_unref["error"] is None

    def test_scene_stratification_without_category_fabrication(self, tmp_path):
        """
        Verifies scene stratification:
        - Where dataset labels support it (Urban, Sparse, Hilly, Forest):
          calculates metrics independently.
        - NEVER fabricates missing categories (e.g. if dataset only has Urban and Forest,
          Sparse and Hilly are strictly omitted).
        - Categories with < 10 samples are strictly excluded.
        """
        h, w = 20, 20
        total_pixels = h * w
        ref = np.linspace(50.0, 150.0, total_pixels, dtype=np.float32).reshape(h, w)
        pred = ref.copy()

        # Build synthetic categorical ground truth labels:
        # Top half (200 px): Urban with +2.0m offset
        # Bottom half (195 px): Forest with -5.0m offset
        # 5 pixels: Hilly (insufficient samples, < 10 px)
        # 0 pixels: Sparse (absent category)
        strata_grid = np.full((h, w), "Urban", dtype=object)
        strata_grid[10:, :] = "Forest"
        strata_grid[0, :5] = "Hilly"  # only 5 pixels

        pred[strata_grid == "Urban"] += 2.0
        pred[strata_grid == "Forest"] -= 5.0
        pred[strata_grid == "Hilly"] += 1.0

        out_prefix = tmp_path / "test_p8_strata"

        (
            metrics,
            err_png,
            abs_png,
            pred_png,
            ref_png,
            hist,
            scatter,
            strata_results,
            active,
            prof
        ) = EvaluationService.evaluate_against_reference(
            predicted_dsm=pred,
            reference_dsm=ref,
            output_prefix=out_prefix,
            strata_labels=strata_grid
        )

        present_categories = [s.landscape_type for s in strata_results]

        # 1. Urban and Forest MUST be present
        assert "Urban" in present_categories
        assert "Forest" in present_categories

        # 2. Hilly had only 5 samples (<10) -> MUST NOT be fabricated or present
        assert "Hilly" not in present_categories

        # 3. Sparse had 0 samples -> MUST NOT be fabricated or present
        assert "Sparse" not in present_categories

        # 4. Metrics must be calculated independently
        urban_metric = next(s for s in strata_results if s.landscape_type == "Urban")
        forest_metric = next(s for s in strata_results if s.landscape_type == "Forest")

        # Urban had +2.0m constant error
        assert urban_metric.sample_count == 195  # 200 - 5
        assert pytest.approx(urban_metric.mae, 0.05) == 2.0
        assert pytest.approx(urban_metric.rmse, 0.05) == 2.0
        assert pytest.approx(urban_metric.bias, 0.05) == 2.0
        assert pytest.approx(urban_metric.median_abs_error, 0.05) == 2.0

        # Forest had -5.0m constant error
        assert forest_metric.sample_count == 200
        assert pytest.approx(forest_metric.mae, 0.05) == 5.0
        assert pytest.approx(forest_metric.rmse, 0.05) == 5.0
        assert pytest.approx(forest_metric.bias, 0.05) == -5.0
        assert pytest.approx(forest_metric.median_abs_error, 0.05) == 5.0

    def test_evaluation_api_response_schema_and_urls(self, tmp_path):
        """
        Verifies that EvaluationResponse contains all Phase 8 fields:
        predicted_map_url, reference_map_url, error_map_url, abs_error_map_url.
        """
        pipeline = PipelineManager.get_instance()
        job_id = "test_phase8_api_job"

        ref = np.linspace(100.0, 150.0, 100, dtype=np.float32).reshape(10, 10)
        pred = ref + 1.5

        ref_file = tmp_path / "truth.npy"
        np.save(ref_file, ref)

        from app.config import settings
        dsm_dir = settings.STORAGE_DIR / "dsm"
        dsm_dir.mkdir(parents=True, exist_ok=True)
        np.save(dsm_dir / f"{job_id}_dsm.npy", pred)

        pipeline.jobs[job_id] = {
            "status": "completed",
            "results": {
                "job_id": job_id,
                "filename": "test.tif",
                "is_georeferenced": False,
                "image_metadata": {
                    "width": 10, "height": 10, "format": "TIF", "file_size_bytes": 1000,
                    "is_georeferenced": False, "crs": None, "transform": None, "bounds": None, "resolution": None
                },
                "dsm_stats": {
                    "min_elevation": 100.0, "max_elevation": 151.5, "mean_elevation": 125.0, "median_elevation": 125.0,
                    "std_elevation": 14.0, "relief": 51.5, "average_slope_deg": 4.0, "max_slope_deg": 8.0,
                    "steep_area_pct": 0.0, "crs": None, "is_metric": True
                },
                "assets": {"dsm_geotiff": "", "dsm_color": "", "hillshade": "", "slope": "", "contour": "", "rgb_texture": ""},
                "dimensions": {
                    "input_width": 10, "input_height": 10, "depth_width": 10, "depth_height": 10,
                    "dsm_width": 10, "dsm_height": 10, "render_grid_width": 10, "render_grid_height": 10
                },
                "mesh_metadata": {
                    "grid_width": 10, "grid_height": 10, "vertex_count": 100, "face_count": 162,
                    "heightfield_url": "", "obj_url": "", "quality": "high"
                }
            },
            "ref_file_path": str(ref_file)
        }

        # Trigger evaluation through PipelineManager
        resp = pipeline.evaluate(job_id, ref_file)

        assert isinstance(resp, EvaluationResponse)
        assert resp.has_evaluation is True
        assert resp.predicted_map_url is not None
        assert "pred_map.png" in resp.predicted_map_url
        assert resp.reference_map_url is not None
        assert "ref_map.png" in resp.reference_map_url
        assert resp.error_map_url is not None
        assert "error_map.png" in resp.error_map_url
        assert resp.abs_error_map_url is not None
        assert "abs_error_map.png" in resp.abs_error_map_url

        # Check artifacts registration
        artifacts = pipeline.get_artifacts(job_id)
        assert "predicted_map" in artifacts
        assert "reference_map" in artifacts
        assert "error_map" in artifacts
        assert "abs_error_map" in artifacts
