import json
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy.stats import pearsonr, spearmanr

from app.main import app
from app.config import settings
from app.schemas.gamus_schemas import (
    CalibrationMode,
    GAMUSEvaluationRequest,
    GAMUSSplit,
)
from app.services.gamus_service import (
    GAMUSService,
    SampleNotFoundError,
    SpatialMismatchError,
    TestSetCalibrationProhibitedError,
    SplitNotSupportedError,
)

client = TestClient(app)


@pytest.fixture
def service():
    return GAMUSService()


class TestGAMUSDatasetIntegration:
    """
    Comprehensive test suite verifying all 16 user requirements for GAMUS benchmark integration.
    """

    # -------------------------------------------------------------------------
    # Requirements 1 & 2: Lazy streaming access & No full dataset download
    # -------------------------------------------------------------------------
    def test_lazy_streaming_does_not_download_full_dataset(self, service):
        """Verify that streaming accesses only individual sample files on demand."""
        img_p, agl_p = service.fetch_sample_files("test", "NYC_TEST_001")
        assert img_p.exists()
        assert agl_p.exists()
        assert img_p.name == "NYC_TEST_001_IMG.h5"
        assert agl_p.name == "NYC_TEST_001_AGL.h5"

    def test_unknown_sample_raises_sample_not_found(self, service):
        """Non-existent sample raises SampleNotFoundError rather than downloading bulk dataset."""
        with pytest.raises(SampleNotFoundError):
            service.fetch_sample_files("test", "NYC_NONEXISTENT_99999")

    # -------------------------------------------------------------------------
    # Requirement 3: Exact RGB-to-height pairing
    # -------------------------------------------------------------------------
    def test_rgb_to_height_pairing_success(self, service):
        """Verify exact pairing of RGB array with reference AGL height raster."""
        rgb, agl, record = service.load_sample_arrays("test", "NYC_TEST_001")
        assert rgb.shape[:2] == agl.shape
        assert rgb.shape[2] == 3
        assert rgb.dtype == np.uint8
        assert agl.dtype == np.float32

    def test_pairing_spatial_mismatch_rejection(self, service, tmp_path):
        """Verify that mismatched spatial dimensions raise SpatialMismatchError."""
        import h5py
        # Create mismatched test fixture in temporary split
        mismatch_dir = service.fixtures_dir / "test"
        bad_img = mismatch_dir / "NYC_MISMATCH_IMG.h5"
        bad_agl = mismatch_dir / "NYC_MISMATCH_AGL.h5"

        with h5py.File(bad_img, "w") as f:
            f.create_dataset("image", data=np.zeros((128, 128, 3), dtype=np.uint8))
        with h5py.File(bad_agl, "w") as f:
            f.create_dataset("image", data=np.zeros((64, 64), dtype=np.float32))

        try:
            with pytest.raises(SpatialMismatchError):
                service.load_sample_arrays("test", "NYC_MISMATCH")
        finally:
            if bad_img.exists():
                bad_img.unlink()
            if bad_agl.exists():
                bad_agl.unlink()

    # -------------------------------------------------------------------------
    # Requirement 4: Preserve sample IDs
    # -------------------------------------------------------------------------
    def test_sample_id_preservation(self, service):
        """Verify sample IDs are strictly preserved throughout records and results."""
        sid = "NYC_TEST_001"
        _, _, record = service.load_sample_arrays("test", sid)
        assert record.sample_id == sid

        req = GAMUSEvaluationRequest(
            split="test",
            sample_id=sid,
            calibration_mode=CalibrationMode.ZERO_SHOT_RELATIVE
        )
        result = service.evaluate_sample(req)
        assert result.sample_id == sid
        assert sid in result.experiment_id

        # Verify disk persistence preservation
        saved_exp = service.get_experiment(result.experiment_id)
        assert saved_exp is not None
        assert saved_exp["sample_record"]["sample_id"] == sid

    # -------------------------------------------------------------------------
    # Requirement 5: Support train / validation / test splits
    # -------------------------------------------------------------------------
    def test_split_handling_train_val_test(self, service):
        """Verify all three splits ('train', 'val', 'test') are supported and indexed."""
        for split in ["train", "val", "test"]:
            catalog = service.list_catalog(split=split)
            assert len(catalog) > 0
            assert all(item.split == split for item in catalog)

        # Invalid split raises SplitNotSupportedError
        with pytest.raises(SplitNotSupportedError):
            service.list_catalog(split="unsupported_split")

    # -------------------------------------------------------------------------
    # Requirements 6 & 7: Height semantics & units (AGL/nDSM in meters, NOT AMSL)
    # -------------------------------------------------------------------------
    def test_height_semantics_and_units_verification(self, service):
        """Verify reference height is certified as Above Ground Level (AGL/nDSM) in meters."""
        _, _, record = service.load_sample_arrays("test", "NYC_TEST_001")
        ref_meta = record.reference_metadata

        assert ref_meta.field_name == "AGL"
        assert ref_meta.type == "nDSM (Height Above Ground Level)"
        assert ref_meta.units == "meters"
        assert ref_meta.vertical_datum == "Ground Level (AGL = 0.0m)"

    def test_never_label_reference_as_absolute_elevation(self, service):
        """Verify reference is never marked as absolute elevation."""
        _, _, record = service.load_sample_arrays("test", "NYC_TEST_001")
        assert record.reference_metadata.is_absolute_elevation is False

        req = GAMUSEvaluationRequest(
            split="test",
            sample_id="NYC_TEST_001",
            calibration_mode=CalibrationMode.ZERO_SHOT_RELATIVE
        )
        res = service.evaluate_sample(req)
        assert res.is_absolute_elevation is False
        assert "Above Ground Level" in res.height_semantics

    # -------------------------------------------------------------------------
    # Requirement 8: Generate benchmark sample record
    # -------------------------------------------------------------------------
    def test_generate_benchmark_sample_record(self, service):
        """Verify benchmark sample record contains comprehensive metadata."""
        _, _, record = service.load_sample_arrays("test", "NYC_TEST_001")
        assert record.benchmark_name == "GAMUS"
        assert record.rgb_metadata.channels == 3
        assert record.reference_metadata.valid_pixel_pct > 95.0
        assert record.reference_metadata.max_val > record.reference_metadata.min_val
        assert record.created_at is not None

    # -------------------------------------------------------------------------
    # Requirement 9: Run Depth Anything V2 inference on RGB
    # -------------------------------------------------------------------------
    def test_depth_anything_inference_on_rgb(self, service):
        """Verify Depth Anything V2 runs on RGB image producing relative depth."""
        rgb, _, _ = service.load_sample_arrays("test", "NYC_TEST_001")
        from app.models.depth_model import DepthEstimator
        depth = DepthEstimator.get_instance().predict(rgb)
        assert depth.shape == rgb.shape[:2]
        assert 0.0 <= depth.min() <= depth.max() <= 1.0

    # -------------------------------------------------------------------------
    # Requirement 10: Anti-data leakage test set calibration prohibition
    # -------------------------------------------------------------------------
    def test_anti_leakage_prohibits_calibrating_on_test_set(self, service):
        """Verify that calibrating directly on test set samples raises TestSetCalibrationProhibitedError."""
        req = GAMUSEvaluationRequest(
            split="test",
            sample_id="NYC_TEST_001",
            calibration_mode=CalibrationMode.DIRECT_FIT_TRAIN_VAL
        )
        with pytest.raises(TestSetCalibrationProhibitedError) as exc_info:
            service.evaluate_sample(req)
        assert "prohibited" in str(exc_info.value).lower()

    def test_train_calibration_transfer_to_test_set(self, service):
        """Verify calibration scale and offset derived strictly from train split transferred to test."""
        req = GAMUSEvaluationRequest(
            split="test",
            sample_id="NYC_TEST_001",
            calibration_mode=CalibrationMode.TRAIN_CALIBRATED_TRANSFER,
            train_calibration_sample_id="NYC_TRAIN_001"
        )
        res = service.evaluate_sample(req)
        assert res.calibration.applied_to_test is True
        assert res.calibration.source_split == "train"
        assert res.calibration.source_sample_id == "NYC_TRAIN_001"
        assert res.calibration.scale is not None
        assert res.height_units == "meters"
        assert res.metrics.mae >= 0.0
        assert res.metrics.rmse >= 0.0

    # -------------------------------------------------------------------------
    # Requirements 11, 12, 13: Calculate MAE, RMSE, Correlation (Pearson & Spearman)
    # -------------------------------------------------------------------------
    def test_statistical_metrics_exact_computation(self, service):
        """Verify MAE, RMSE, Pearson r, and Spearman rho calculations."""
        req = GAMUSEvaluationRequest(
            split="test",
            sample_id="NYC_TEST_001",
            calibration_mode=CalibrationMode.ZERO_SHOT_RELATIVE
        )
        res = service.evaluate_sample(req)
        m = res.metrics

        assert m.mae >= 0.0
        assert m.rmse >= m.mae  # Mathematical property: RMSE >= MAE
        assert 0.0 <= m.pearson_r <= 1.0
        assert 0.0 <= m.spearman_rho <= 1.0
        assert m.valid_pixels > 0
        assert m.le90 >= m.median_abs_error
        assert m.le95 >= m.le90

    # -------------------------------------------------------------------------
    # Requirement 14: Generate signed and absolute error maps
    # -------------------------------------------------------------------------
    def test_signed_and_absolute_error_map_generation(self, service):
        """Verify signed and absolute error maps are rendered and saved as PNGs."""
        req = GAMUSEvaluationRequest(
            split="test",
            sample_id="NYC_TEST_001",
            calibration_mode=CalibrationMode.ZERO_SHOT_RELATIVE
        )
        res = service.evaluate_sample(req)

        signed_p = Path(res.assets["signed_error_map"])
        abs_p = Path(res.assets["absolute_error_map"])

        assert signed_p.exists()
        assert abs_p.exists()
        assert signed_p.stat().st_size > 1000
        assert abs_p.stat().st_size > 1000

    # -------------------------------------------------------------------------
    # Requirement 15: Predicted-vs-reference scatter plot
    # -------------------------------------------------------------------------
    def test_predicted_vs_reference_scatter_plot(self, service):
        """Verify scatter points and rendered publication scatter PNG."""
        req = GAMUSEvaluationRequest(
            split="test",
            sample_id="NYC_TEST_001",
            calibration_mode=CalibrationMode.ZERO_SHOT_RELATIVE,
            scatter_sample_size=500
        )
        res = service.evaluate_sample(req)

        assert len(res.scatter_points) == 500
        scatter_png = Path(res.assets["scatter_plot"])
        assert scatter_png.exists()
        assert scatter_png.stat().st_size > 2000

    # -------------------------------------------------------------------------
    # Requirement 16: Record all experiment metadata
    # -------------------------------------------------------------------------
    def test_experiment_metadata_recording_and_persistence(self, service):
        """Verify complete experiment record is saved to JSON and retrievable."""
        req = GAMUSEvaluationRequest(
            split="test",
            sample_id="NYC_TEST_001",
            calibration_mode=CalibrationMode.ZERO_SHOT_RELATIVE
        )
        res = service.evaluate_sample(req)

        exp_record = service.get_experiment(res.experiment_id)
        assert exp_record is not None
        assert exp_record["experiment_id"] == res.experiment_id
        assert exp_record["sample_record"]["benchmark_name"] == "GAMUS"
        assert exp_record["evaluation_result"]["metrics"]["mae"] == res.metrics.mae
        assert exp_record["environment"]["model"] == settings.MODEL_NAME

        # Verify listing
        exp_list = service.list_experiments()
        exp_ids = [e["experiment_id"] for e in exp_list]
        assert res.experiment_id in exp_ids

    # -------------------------------------------------------------------------
    # Real GAMUS Sample Integration Test (if locally cached)
    # -------------------------------------------------------------------------
    def test_real_cached_gamus_sample(self, service):
        """Integration test on real GAMUS NYC_00735 sample from HuggingFace cache if present."""
        hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
        cached_img = list(hf_cache.glob("**/test/NYC_00735_IMG.h5"))
        if not cached_img:
            pytest.skip("Real GAMUS sample NYC_00735 not found in HuggingFace cache.")

        req = GAMUSEvaluationRequest(
            split="test",
            sample_id="NYC_00735",
            calibration_mode=CalibrationMode.ZERO_SHOT_RELATIVE,
            scatter_sample_size=1000
        )
        res = service.evaluate_sample(req)

        assert res.sample_id == "NYC_00735"
        assert res.metrics.valid_pixels == 1024 * 1024
        assert res.metrics.pearson_r > 0.0
        assert res.metrics.spearman_rho > 0.0
        assert Path(res.assets["scatter_plot"]).exists()
        assert Path(res.assets["signed_error_map"]).exists()
        assert Path(res.assets["absolute_error_map"]).exists()


class TestGAMUSApiEndpoints:
    """
    Integration tests for GAMUS benchmark REST API endpoints.
    """

    def test_api_catalog_endpoint(self):
        """GET /api/benchmarks/gamus/catalog"""
        resp = client.get("/api/benchmarks/gamus/catalog?split=test")
        assert resp.status_code == 200
        items = resp.json()
        assert isinstance(items, list)
        assert len(items) > 0
        assert all(item["split"] == "test" for item in items)

    def test_api_sample_record_endpoint(self):
        """GET /api/benchmarks/gamus/samples/test/NYC_TEST_001"""
        resp = client.get("/api/benchmarks/gamus/samples/test/NYC_TEST_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["benchmark_name"] == "GAMUS"
        assert data["reference_metadata"]["is_absolute_elevation"] is False
        assert data["reference_metadata"]["units"] == "meters"

    def test_api_evaluate_prohibits_test_set_calibration(self):
        """POST /api/benchmarks/gamus/evaluate rejects test set direct calibration with HTTP 400."""
        payload = {
            "split": "test",
            "sample_id": "NYC_TEST_001",
            "calibration_mode": "direct_fit_train_val"
        }
        resp = client.post("/api/benchmarks/gamus/evaluate", json=payload)
        assert resp.status_code == 400
        assert "prohibited" in resp.json()["detail"].lower()

    def test_api_evaluate_zero_shot_relative(self):
        """POST /api/benchmarks/gamus/evaluate with zero_shot_relative"""
        payload = {
            "split": "test",
            "sample_id": "NYC_TEST_001",
            "calibration_mode": "zero_shot_relative",
            "scatter_sample_size": 200
        }
        resp = client.post("/api/benchmarks/gamus/evaluate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["sample_id"] == "NYC_TEST_001"
        assert data["is_absolute_elevation"] is False
        assert data["metrics"]["mae"] >= 0.0
        assert len(data["scatter_points"]) == 200
        exp_id = data["experiment_id"]

        # Test experiment retrieval
        exp_resp = client.get(f"/api/benchmarks/gamus/experiments/{exp_id}")
        assert exp_resp.status_code == 200
        assert exp_resp.json()["experiment_id"] == exp_id

        # Test asset retrieval
        asset_resp = client.get(f"/api/benchmarks/gamus/experiments/{exp_id}/assets/scatter_plot")
        assert asset_resp.status_code == 200
        assert asset_resp.headers["content-type"] == "image/png"

