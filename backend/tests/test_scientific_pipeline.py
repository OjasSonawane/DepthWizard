import os
import math
import tempfile
from pathlib import Path
import numpy as np
import pytest
import cv2
import rasterio
from rasterio.transform import from_origin
from affine import Affine

from app.services.geospatial_service import GeospatialService
from app.services.calibration_service import (
    CalibrationService,
    RelativeCalibrationStrategy,
    DEMCalibrationStrategy,
    GCPCalibrationStrategy,
    ScaledEstimateCalibrationStrategy
)
from app.services.dsm_service import DSMService
from app.services.evaluation_service import EvaluationService
from app.models.depth_model import DepthEstimator
from app.schemas.schemas import GCPItem


class TestGeospatialAndMetadata:
    """Tests 1, 2, 3: Ingestion, Validation, and Raster Metadata Extraction."""

    def test_geodesic_resolution_equator(self):
        """EPSG:4326 resolution in degrees at equator must convert to ~111,320m per degree."""
        res_deg = (0.001, 0.001)
        bounds_equator = [-10.0, -1.0, 10.0, 1.0]  # center lat = 0.0
        dx_m, dy_m = GeospatialService.get_ground_resolution_meters(
            resolution=res_deg,
            crs_str="EPSG:4326",
            bounds=bounds_equator
        )
        assert pytest.approx(dx_m, rel=1e-3) == 0.001 * 111320.0  # ~111.32m
        assert pytest.approx(dy_m, rel=1e-3) == 0.001 * 110540.0  # ~110.54m

    def test_geodesic_resolution_latitude_45(self):
        """At 45° latitude, dx_m must shrink by cos(45°)."""
        res_deg = (0.001, 0.001)
        bounds_45 = [0.0, 44.0, 1.0, 46.0]  # center lat = 45.0
        dx_m, dy_m = GeospatialService.get_ground_resolution_meters(
            resolution=res_deg,
            crs_str="EPSG:4326",
            bounds=bounds_45
        )
        expected_dx = 0.001 * 111320.0 * math.cos(math.radians(45.0))
        assert pytest.approx(dx_m, rel=1e-3) == expected_dx
        assert pytest.approx(dy_m, rel=1e-3) == 110.54

    def test_projected_resolution_preserves_meters(self):
        """Projected UTM CRS native resolution is already in meters and must not be altered."""
        res_utm = (0.5, 0.5)
        dx_m, dy_m = GeospatialService.get_ground_resolution_meters(
            resolution=res_utm,
            crs_str="EPSG:32643",
            bounds=[500000.0, 3000000.0, 501000.0, 3001000.0]
        )
        assert dx_m == 0.5
        assert dy_m == 0.5

    def test_reproject_coords_lonlat_to_utm(self):
        """PyProj Transformer reprojection from WGS84 to UTM Zone 43N."""
        utm_x, utm_y = GeospatialService.reproject_coords(
            x=77.0,
            y=32.0,
            from_crs_str="EPSG:4326",
            to_crs_str="EPSG:32643"
        )
        assert 680000.0 < utm_x < 700000.0
        assert 3500000.0 < utm_y < 3600000.0

    def test_image_validation_low_resolution_warning(self, tmp_path):
        """Images below recommended resolution must trigger descriptive warning."""
        small_img = np.zeros((128, 128, 3), dtype=np.uint8)
        img_path = tmp_path / "low_res.png"
        cv2.imwrite(str(img_path), small_img)

        meta, rgb = GeospatialService.inspect_file(img_path)
        assert meta.is_low_resolution is True
        assert meta.resolution_warning is not None
        assert rgb.shape == (128, 128, 3)


class TestDepthEstimationAndNormalization:
    """Tests 4 & 5: Monocular Depth Inference and Normalization."""

    def test_percentile_normalization_outlier_rejection(self):
        """Percentile normalization must map 1st-99th percentile to [0.0, 1.0], clipping outliers."""
        estimator = DepthEstimator()
        arr = np.linspace(100.0, 200.0, 1000).astype(np.float32)
        arr[0] = -9999.0
        arr[-1] = 9999.0

        norm = estimator.normalize_depth(arr)
        assert np.isfinite(norm).all()
        assert norm.min() >= 0.0
        assert norm.max() <= 1.0
        assert norm[500] > norm[200]

    def test_neural_inference_shape_and_range(self):
        """Actual Depth Anything V2 neural inference on RGB image produces normalized [0, 1] output."""
        estimator = DepthEstimator.get_instance()
        assert estimator.is_loaded is True
        assert estimator.is_fallback is False

        img = (np.random.rand(128, 128, 3) * 255).astype(np.uint8)
        depth = estimator.predict(img)

        assert depth.shape == (128, 128)
        assert depth.dtype == np.float32
        assert np.isfinite(depth).all()
        assert 0.0 <= depth.min() <= 0.1
        assert 0.9 <= depth.max() <= 1.0


class TestScaleCalibrationStrategies:
    """Tests 6, 7, 8: Calibration Strategy Pattern, Huber Regression, GCP Reprojection."""

    def test_relative_calibration_strategy(self):
        """Relative strategy must output normalized relative relief [0..1]."""
        depth = np.array([[0.0, 0.5], [0.8, 1.0]], dtype=np.float32)
        strategy = RelativeCalibrationStrategy()
        dsm, result = strategy.calibrate(depth)

        assert result.method == "relative"
        assert result.is_metric is False
        assert result.scale == 100.0
        assert result.offset == 0.0
        assert dsm.min() == 0.0
        assert dsm.max() == 100.0
        np.testing.assert_allclose(dsm, depth * 100.0)

    def test_dem_huber_calibration_exact_fit(self):
        """DEM calibration with Huber regression must accurately recover true slope and intercept."""
        np.random.seed(42)
        depth = np.random.uniform(0.1, 0.9, (100, 100)).astype(np.float32)
        true_scale = 80.0
        true_offset = 1200.0
        ref_dem = (true_scale * depth + true_offset).astype(np.float32)

        strategy = DEMCalibrationStrategy()
        dsm, result = strategy.calibrate(depth, reference_dem=ref_dem)

        assert result.is_metric is True
        assert pytest.approx(result.scale, abs=0.5) == true_scale
        assert pytest.approx(result.offset, abs=0.5) == true_offset
        assert pytest.approx(result.r2, abs=0.01) == 1.0

    def test_dem_huber_calibration_outlier_immunity(self):
        """Huber loss must resist extreme corrupted outlier points where OLS would fail."""
        depth = np.linspace(0.0, 1.0, 500).astype(np.float32).reshape(50, 10)
        true_scale = 100.0
        true_offset = 500.0
        ref_dem = (true_scale * depth + true_offset).astype(np.float32)

        # Corrupt 5% of pixels with massive noise spikes
        ref_dem[5, :] += 5000.0
        ref_dem[25, :] -= 5000.0

        strategy = DEMCalibrationStrategy()
        dsm, result = strategy.calibrate(depth, reference_dem=ref_dem)

        assert pytest.approx(result.scale, rel=0.10) == true_scale
        assert pytest.approx(result.offset, rel=0.10) == true_offset

    def test_dem_calibration_polarity_inversion(self):
        """When relative depth gradient is anti-correlated with reference elevation, polarity is flipped."""
        depth = np.linspace(0.0, 1.0, 100).astype(np.float32).reshape(10, 10)
        ref_dem = (-75.0 * depth + 1500.0).astype(np.float32)

        strategy = DEMCalibrationStrategy()
        dsm, result = strategy.calibrate(depth, reference_dem=ref_dem)

        assert "inverted polarity" in result.message
        assert result.scale > 0.0
        assert result.is_metric is True

    def test_gcp_calibration_with_geodetic_reprojection(self):
        """GCPs entered in WGS84 lon/lat degrees are accurately transformed to UTM coordinates."""
        transform = [1.0, 0.0, 500000.0, 0.0, -1.0, 3500100.0]
        crs_str = "EPSG:32643"
        depth = np.random.uniform(0.0, 1.0, (100, 100)).astype(np.float32)

        from pyproj import Transformer
        to_wgs84 = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
        gcps = []
        sample_pixels = [(20, 20), (50, 50), (80, 80)]
        for r, c in sample_pixels:
            utm_x = 500000.0 + c * 1.0
            utm_y = 3500100.0 - r * 1.0
            lon, lat = to_wgs84.transform(utm_x, utm_y)
            elev = 1000.0 + depth[r, c] * 50.0
            gcps.append(GCPItem(id=f"gcp_{len(gcps)+1}", x=lon, y=lat, elevation=float(elev)))

        strategy = GCPCalibrationStrategy()
        dsm, result = strategy.calibrate(depth, gcps=gcps, transform_list=transform, crs_str=crs_str)

        assert result.method == "gcp"
        assert result.is_metric is True
        assert pytest.approx(result.scale, abs=2.0) == 50.0
        assert pytest.approx(result.offset, abs=2.0) == 1000.0


class TestTerrainDerivatives:
    """Tests 8 & 12: Horn's Slope, Riley's TRI, Hillshade."""

    def test_horns_slope_exact_45_degree_ramp(self):
        """Horn's algorithm on an analytical 45° planar ramp z(x) = x * cell_x must yield 45.0°."""
        cell_size = 5.0
        h, w = 50, 50
        x_coords = np.arange(w, dtype=np.float32) * cell_size
        ramp_dsm = np.tile(x_coords, (h, 1))

        slope_deg = EvaluationService.calculate_horn_slope(ramp_dsm, cell_size=cell_size)

        interior_slope = slope_deg[2:-2, 2:-2]
        np.testing.assert_allclose(interior_slope, 45.0, atol=0.05)

    def test_horns_slope_flat_surface(self):
        """Horn's slope on a flat horizontal surface must be strictly 0.0°."""
        flat_dsm = np.full((30, 30), 250.0, dtype=np.float32)
        slope_deg = EvaluationService.calculate_horn_slope(flat_dsm, cell_size=10.0)
        np.testing.assert_allclose(slope_deg[1:-1, 1:-1], 0.0, atol=1e-4)

    def test_riley_terrain_ruggedness_index_flat(self):
        """Riley (1999) TRI on a flat surface must be 0.0."""
        flat_dsm = np.full((20, 20), 500.0, dtype=np.float32)
        tri_map = DSMService.compute_riley_tri(flat_dsm)
        np.testing.assert_allclose(tri_map[1:-1, 1:-1], 0.0, atol=1e-5)

    def test_riley_terrain_ruggedness_index_single_peak(self):
        """
        On an isolated peak z_0 = 10 surrounded by 8 neighbors of 0:
        TRI = sqrt( 8 * (0 - 10)^2 ) = sqrt(800) ~= 28.28427.
        """
        grid = np.zeros((5, 5), dtype=np.float32)
        grid[2, 2] = 10.0
        tri_map = DSMService.compute_riley_tri(grid)
        expected_tri = math.sqrt(8.0 * (10.0 ** 2))
        assert pytest.approx(tri_map[2, 2], rel=1e-4) == expected_tri

    def test_hillshade_flat_surface_illumination(self):
        """
        Hillshade on flat surface with sun altitude 45°:
        cos(incidence) = cos(zenith) = cos(90° - 45°) = cos(45°) ~= 0.7071.
        Output hillshade = 255 * 0.7071 ~= 180.
        """
        flat_dsm = np.full((20, 20), 100.0, dtype=np.float32)
        slope_deg, hillshade = DSMService.compute_slope_and_hillshade(
            flat_dsm,
            resolution=(1.0, 1.0),
            sun_azimuth_deg=315.0,
            sun_altitude_deg=45.0
        )
        expected_val = int(round(255.0 * math.cos(math.radians(45.0))))
        assert abs(int(hillshade[5, 5]) - expected_val) <= 1


class TestValidationAndErrorMetrics:
    """Tests 9, 10, 11, 12: MAE, RMSE, Pearson r, R2, MBE, LE90, LE95, Error Maps."""

    def test_statistical_metrics_exact_computation(self, tmp_path):
        """Validate MAE, RMSE, MBE, R2, LE90, LE95 against exact mathematical formulas."""
        ref = np.arange(100, dtype=np.float32).reshape(10, 10) + 100.0
        pred = ref + 3.0

        out_prefix = tmp_path / "test_eval"
        metrics, err_png, abs_png, pred_png, ref_png, hist, scatter, landscape, active, prof = EvaluationService.evaluate_against_reference(
            predicted_dsm=pred,
            reference_dsm=ref,
            output_prefix=out_prefix
        )

        assert metrics.mae == 3.0
        assert metrics.rmse == 3.0
        assert metrics.mbe == 3.0
        assert metrics.pearson_r == 1.0
        assert pytest.approx(metrics.r2, abs=0.01) == 0.989
        assert metrics.le90 == 3.0
        assert metrics.le95 == 3.0
        assert err_png.exists()
        assert abs_png.exists()
        assert pred_png.exists()
        assert ref_png.exists()

    def test_monocular_depth_benchmark_metrics(self, tmp_path):
        """Validate AbsRel, SqRel, delta1, delta2, delta3."""
        ref = np.full((10, 10), 100.0, dtype=np.float32)
        pred = np.full((10, 10), 110.0, dtype=np.float32)

        out_prefix = tmp_path / "test_mono"
        metrics, *_ = EvaluationService.evaluate_against_reference(
            predicted_dsm=pred,
            reference_dsm=ref,
            output_prefix=out_prefix
        )

        assert pytest.approx(metrics.abs_rel, abs=1e-3) == 0.10
        assert pytest.approx(metrics.sq_rel, abs=1e-3) == 1.0
        assert metrics.delta1 == 100.0
        assert metrics.delta2 == 100.0
        assert metrics.delta3 == 100.0


class TestGeoTIFFExportAndRoundtrip:
    """Test 13: High-precision GeoTIFF export and roundtrip verification."""

    def test_geotiff_export_spatial_preservation(self, tmp_path):
        """Save GeoTIFF with CRS and Affine transform, reopen, and verify spatial and numerical fidelity."""
        h, w = 64, 64
        data = np.linspace(100.0, 500.0, h * w, dtype=np.float32).reshape(h, w)
        transform = [10.0, 0.0, 300000.0, 0.0, -10.0, 4000000.0]
        crs_str = "EPSG:32643"
        out_tif = tmp_path / "exported_dsm.tif"

        GeospatialService.save_geotiff(
            output_path=out_tif,
            data=data,
            crs_str=crs_str,
            transform_list=transform
        )

        assert out_tif.exists()

        with rasterio.open(out_tif) as src:
            assert src.crs.to_string() == crs_str
            assert src.width == w
            assert src.height == h
            assert src.transform.a == transform[0]
            assert src.transform.c == transform[2]
            assert src.transform.e == transform[4]
            assert src.transform.f == transform[5]
            read_arr = src.read(1)
            np.testing.assert_allclose(read_arr, data, rtol=1e-6)

