import numpy as np
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.services.evaluation_service import EvaluationService
from app.services.depth_service import PipelineManager

client = TestClient(app)

class TestConfigurableMetrics:
    def test_synthetic_evaluation_metrics(self, tmp_path):
        """
        Verify mathematical correctness of metrics against known ground truth arrays.
        """
        # Create known reference and predicted rasters
        ref = np.array([
            [10.0, 20.0, 30.0],
            [15.0, 25.0, 35.0],
            [20.0, 30.0, 40.0]
        ], dtype=np.float32)
        # Tile to 10x10 to exceed minimum 30 pixels
        ref = np.tile(ref, (4, 4))[:10, :10]
        # Predicted has constant offset of +2.0m on half the pixels, -1.0m on other half
        pred = ref.copy()
        pred[:5, :] += 2.0
        pred[5:, :] -= 1.0

        output_prefix = tmp_path / "test_eval"

        metrics, err_png, abs_png, pred_png, ref_png, hist, scatter, landscape, active, prof = EvaluationService.evaluate_against_reference(
            predicted_dsm=pred,
            reference_dsm=ref,
            output_prefix=output_prefix,
            profile="terrain_comprehensive"
        )

        # Expected errors: 50 pixels with +2.0, 50 pixels with -1.0
        # MAE = (50*2 + 50*1) / 100 = 1.5
        assert pytest.approx(metrics.mae, 0.05) == 1.5
        # RMSE = sqrt((50*4 + 50*1) / 100) = sqrt(2.5) ≈ 1.58
        assert pytest.approx(metrics.rmse, 0.05) == 1.58
        # MBE = (50*2 - 50*1) / 100 = 0.5
        assert pytest.approx(metrics.mbe, 0.05) == 0.5

        # Pearson r should be extremely high since terrain slope is preserved
        assert metrics.pearson_r > 0.95
        # R2 should also be high
        assert metrics.r2 > 0.90

        # LE90: 90% percentile of [1.0 (50%), 2.0 (50%)] -> 2.0
        assert metrics.le90 >= 1.9

        # Monocular depth metrics (ref > 0)
        assert metrics.abs_rel is not None
        assert metrics.sq_rel is not None
        assert metrics.delta1 is not None
        assert metrics.delta1 > 80.0  # ratio max(pred/ref, ref/pred) is well within 1.25

        # Slope metrics
        assert metrics.slope_mae is not None
        assert metrics.slope_rmse is not None

        # Check file outputs
        assert err_png.exists()
        assert abs_png.exists()
        assert pred_png.exists()
        assert ref_png.exists()
        assert len(hist) > 0
        assert len(scatter) > 0

    def test_metric_profiles_selection(self, tmp_path):
        """Verifies that selecting different profiles returns expected active metrics."""
        ref = np.tile(np.linspace(10, 50, 8), (8, 1)).astype(np.float32)
        pred = ref + 1.0
        output_prefix = tmp_path / "profile_eval"

        # Basic Terrain Profile
        *_, active_basic, prof_basic = EvaluationService.evaluate_against_reference(
            pred, ref, output_prefix, profile="terrain_basic"
        )
        assert prof_basic == "terrain_basic"
        assert set(active_basic) == {"mae", "rmse", "pearson_r", "mbe"}

        # Depth Benchmark Profile
        *_, active_depth, prof_depth = EvaluationService.evaluate_against_reference(
            pred, ref, output_prefix, profile="depth_benchmark"
        )
        assert prof_depth == "depth_benchmark"
        assert "abs_rel" in active_depth
        assert "delta1" in active_depth

        # Custom Metrics Profile
        custom_choice = ["mae", "r2", "le90"]
        *_, active_custom, prof_custom = EvaluationService.evaluate_against_reference(
            pred, ref, output_prefix, profile="custom", selected_metrics=custom_choice
        )
        assert prof_custom == "custom"
        assert active_custom == custom_choice

    def test_configure_api_endpoint(self, tmp_path):
        """Tests POST /api/evaluate/{job_id}/configure."""
        # Set up a mock completed job with saved DSM and reference
        pipeline = PipelineManager.get_instance()
        job_id = "test_eval_job_1"
        pipeline.jobs[job_id] = {
            "status": "completed",
            "results": {
                "job_id": job_id,
                "filename": "test.png",
                "is_georeferenced": False,
                "image_metadata": {
                    "filename": "test.png",
                    "width": 64,
                    "height": 64,
                    "band_count": 3,
                    "datatype": "uint8",
                    "is_georeferenced": False
                },
                "calibration": {
                    "method": "relative",
                    "is_metric": False,
                    "scale": 1.0,
                    "offset": 0.0,
                    "r2": 0.0,
                    "rmse": 0.0,
                    "gcp_count": 0,
                    "confidence": "high",
                    "message": "Relative"
                },
                "dsm_stats": {
                    "min_elevation": 10.0,
                    "max_elevation": 50.0,
                    "mean_elevation": 30.0,
                    "median_elevation": 30.0,
                    "std_elevation": 10.0,
                    "relief": 40.0,
                    "average_slope_deg": 12.0,
                    "max_slope_deg": 35.0,
                    "steep_area_pct": 5.0,
                    "is_metric": False
                },
                "disaster_risk": {
                    "low_lying_area_pct": 10.0,
                    "steep_slope_hazard_pct": 5.0,
                    "moderate_slope_pct": 20.0,
                    "gentle_slope_pct": 75.0,
                    "ruggedness_index": 0.2,
                    "elevation_thresholds": {}
                },
                "mesh_metadata": {
                    "grid_width": 64,
                    "grid_height": 64,
                    "vertex_count": 4096,
                    "face_count": 8000,
                    "heightfield_url": "/mesh.json",
                    "obj_url": "/mesh.obj"
                },
                "assets": {},
                "timing_seconds": {},
                "device_used": "cpu"
            }
        }

        # Save synthetic DSM
        from app.config import settings
        settings.DSM_DIR.mkdir(parents=True, exist_ok=True)
        dsm_arr = np.linspace(10, 50, 64 * 64, dtype=np.float32).reshape((64, 64))
        np.save(settings.DSM_DIR / f"{job_id}_dsm.npy", dsm_arr)

        # Save reference file
        ref_file = tmp_path / "reference.npy"
        np.save(ref_file, dsm_arr + 2.0)
        pipeline.jobs[job_id]["ref_file_path"] = str(ref_file)

        # Call configure endpoint
        resp = client.post(
            f"/api/evaluate/{job_id}/configure",
            json={"profile": "terrain_basic"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_evaluation"] is True
        assert data["profile_name"] == "terrain_basic"
        assert set(data["selected_metrics"]) == {"mae", "rmse", "pearson_r", "mbe"}
        assert data["metrics"]["mae"] == 2.0

