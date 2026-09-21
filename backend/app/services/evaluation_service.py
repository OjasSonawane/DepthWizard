import logging
from pathlib import Path
from typing import Tuple, Dict, Any, Optional, List, Union
import numpy as np
import cv2
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.cm as cm
from scipy.stats import pearsonr

from app.schemas.schemas import EvaluationMetrics, EvaluationResponse, LandscapeMetric

logger = logging.getLogger("depthwizard.evaluation")

class EvaluationService:
    METRIC_PROFILES: Dict[str, List[str]] = {
        "terrain_basic": ["mae", "rmse", "pearson_r", "mbe"],
        "terrain_standard": [
            "mae", "rmse", "pearson_r", "mbe", "median_abs_error",
            "max_abs_error", "r2", "valid_pixel_pct"
        ],
        "terrain_comprehensive": [
            "mae", "rmse", "pearson_r", "mbe", "mean_error", "median_error",
            "median_abs_error", "max_abs_error", "r2", "valid_pixel_pct",
            "le90", "le95", "slope_mae", "slope_rmse"
        ],
        "depth_benchmark": [
            "abs_rel", "sq_rel", "delta1", "delta2", "delta3", "rmse", "mae"
        ],
        "custom": []
    }

    @staticmethod
    def calculate_horn_slope(
        elevation_grid: np.ndarray,
        cell_size: Union[float, Tuple[float, float]] = 1.0
    ) -> np.ndarray:
        """
        Computes terrain slope in degrees using Horn's 1981 algorithm (standard in GDAL/ArcGIS).
        cell_size can be a scalar or (cell_size_x, cell_size_y) in meters.
        """
        if isinstance(cell_size, (tuple, list)):
            cell_x = abs(float(cell_size[0])) if len(cell_size) > 0 and cell_size[0] > 0 else 1.0
            cell_y = abs(float(cell_size[1])) if len(cell_size) > 1 and cell_size[1] > 0 else cell_x
        else:
            cell_x = cell_y = abs(float(cell_size)) if cell_size > 0 else 1.0

        valid_mask = np.isfinite(elevation_grid) & (elevation_grid > -9000.0)
        clean = np.where(valid_mask, elevation_grid, np.nanmean(elevation_grid[valid_mask]) if np.any(valid_mask) else 0.0)

        kx = np.array([
            [-1.0, 0.0, 1.0],
            [-2.0, 0.0, 2.0],
            [-1.0, 0.0, 1.0]
        ], dtype=np.float64) / (8.0 * max(0.0001, cell_x))

        ky = np.array([
            [-1.0, -2.0, -1.0],
            [ 0.0,  0.0,  0.0],
            [ 1.0,  2.0,  1.0]
        ], dtype=np.float64) / (8.0 * max(0.0001, cell_y))

        dz_dx = cv2.filter2D(clean.astype(np.float64), -1, kx)
        dz_dy = cv2.filter2D(clean.astype(np.float64), -1, ky)
        slope_rad = np.arctan(np.hypot(dz_dx, dz_dy))
        slope_deg = np.degrees(slope_rad)
        slope_deg[~valid_mask] = np.nan
        return slope_deg

    @staticmethod
    def evaluate_against_reference(
        predicted_dsm: np.ndarray,
        reference_dsm: np.ndarray,
        output_prefix: Path,
        profile: Optional[str] = "terrain_standard",
        selected_metrics: Optional[List[str]] = None,
        crs: Optional[str] = None,
        transform: Optional[Any] = None,
        strata_labels: Optional[Union[np.ndarray, Dict[str, np.ndarray]]] = None
    ) -> Tuple[
        EvaluationMetrics,
        Path, Path, Path, Path,
        List[Dict[str, Any]],
        List[Dict[str, float]],
        List[LandscapeMetric],
        List[str],
        str
    ]:
        """
        Calculates configurable scientific validation metrics:
        Elevation: MAE, RMSE, Pearson r, R2, MBE, Median Error, Median AE, Max AE, LE90, LE95.
        Monocular Depth: AbsRel, SqRel, delta1, delta2, delta3.
        Slope: Slope MAE, Slope RMSE (Horn's method).
        Generates:
        - Diverging signed error map PNG & GeoTIFF
        - Absolute error map PNG & GeoTIFF
        - Predicted elevation map PNG
        - Reference elevation map PNG
        - Subsampled scatter plot coordinates
        - Scene stratification breakdown (Urban, Sparse, Hilly, Forest)
        """
        # Ensure identical spatial grid
        if predicted_dsm.shape != reference_dsm.shape:
            ref_aligned = cv2.resize(
                reference_dsm,
                (predicted_dsm.shape[1], predicted_dsm.shape[0]),
                interpolation=cv2.INTER_LINEAR
            )
        else:
            ref_aligned = reference_dsm

        # Valid overlap mask (finite and non-nodata)
        valid = (
            np.isfinite(predicted_dsm) &
            np.isfinite(ref_aligned) &
            (ref_aligned > -9000.0) &
            (predicted_dsm > -9000.0)
        )

        n_valid = int(np.count_nonzero(valid))
        if n_valid < 30:
            raise ValueError(f"Insufficient valid overlapping pixels for evaluation ({n_valid} found). Both rasters must share coverage.")

        pred_vals = predicted_dsm[valid].astype(np.float64)
        ref_vals = ref_aligned[valid].astype(np.float64)

        # 1. Elevation metrics
        errors = pred_vals - ref_vals
        abs_errors = np.abs(errors)

        mae = float(np.mean(abs_errors))
        rmse = float(np.sqrt(np.mean(errors ** 2)))
        mbe = float(np.mean(errors))
        median_err = float(np.median(errors))
        median_abs_err = float(np.median(abs_errors))
        max_abs_err = float(np.max(abs_errors))
        min_err = float(np.min(errors))
        max_err = float(np.max(errors))

        try:
            r_val, _ = pearsonr(pred_vals, ref_vals)
            pearson_r = float(r_val) if np.isfinite(r_val) else 0.0
        except Exception:
            pearson_r = 0.0

        # R2 Coefficient of Determination
        ss_tot = float(np.sum((ref_vals - np.mean(ref_vals)) ** 2))
        ss_res = float(np.sum((ref_vals - pred_vals) ** 2))
        if ss_tot > 1e-9:
            r2_score = float(max(-10.0, 1.0 - (ss_res / ss_tot)))
        else:
            r2_score = 0.0

        # LE90 and LE95 (90th and 95th percentile absolute errors)
        le90_val = float(np.percentile(abs_errors, 90))
        le95_val = float(np.percentile(abs_errors, 95))

        total_pixels = int(predicted_dsm.size)
        valid_pixel_pct = round(float(n_valid / max(1, total_pixels) * 100.0), 2)

        # 2. Monocular Depth Benchmark Metrics (for positive depths/elevations)
        pos_mask = (ref_vals > 0.0) & (pred_vals > 0.0)
        n_pos = int(np.count_nonzero(pos_mask))
        if n_pos >= 10:
            p_pos = pred_vals[pos_mask]
            r_pos = ref_vals[pos_mask]
            abs_rel = float(np.mean(np.abs(p_pos - r_pos) / r_pos))
            sq_rel = float(np.mean(((p_pos - r_pos) ** 2) / r_pos))
            ratios = np.maximum(p_pos / r_pos, r_pos / p_pos)
            delta1 = float(np.mean(ratios < 1.25) * 100.0)
            delta2 = float(np.mean(ratios < (1.25 ** 2)) * 100.0)
            delta3 = float(np.mean(ratios < (1.25 ** 3)) * 100.0)
        else:
            abs_rel = None
            sq_rel = None
            delta1 = None
            delta2 = None
            delta3 = None

        # 3. Slope Metrics via Horn's Algorithm
        cell_size = (1.0, 1.0)
        if transform is not None:
            try:
                from app.services.geospatial_service import GeospatialService
                if hasattr(transform, 'a') and hasattr(transform, 'e'):
                    raw_res = (abs(transform.a), abs(transform.e))
                elif isinstance(transform, (list, tuple)) and len(transform) >= 5:
                    raw_res = (abs(transform[0]), abs(transform[4]))
                else:
                    raw_res = (1.0, 1.0)
                cell_size = GeospatialService.get_ground_resolution_meters(raw_res, crs)
            except Exception:
                cell_size = (1.0, 1.0)

        pred_slope_grid = EvaluationService.calculate_horn_slope(predicted_dsm, cell_size=cell_size)
        ref_slope_grid = EvaluationService.calculate_horn_slope(ref_aligned, cell_size=cell_size)

        # Exclude 1-pixel border to eliminate filter boundary artifacts
        valid_slope = valid.copy()
        valid_slope[0, :] = False
        valid_slope[-1, :] = False
        valid_slope[:, 0] = False
        valid_slope[:, -1] = False

        if np.count_nonzero(valid_slope) >= 10:
            p_slope = pred_slope_grid[valid_slope]
            r_slope = ref_slope_grid[valid_slope]
            slope_diff = np.abs(p_slope - r_slope)
            slope_mae = float(np.mean(slope_diff))
            slope_rmse = float(np.sqrt(np.mean(slope_diff ** 2)))
        else:
            slope_mae = None
            slope_rmse = None

        metrics = EvaluationMetrics(
            mae=round(mae, 2),
            rmse=round(rmse, 2),
            pearson_r=round(pearson_r, 3),
            mbe=round(mbe, 2),
            mean_error=round(mbe, 2),
            median_error=round(median_err, 2),
            median_abs_error=round(median_abs_err, 2),
            max_abs_error=round(max_abs_err, 2),
            min_error=round(min_err, 2),
            max_error=round(max_err, 2),
            r2=round(r2_score, 3),
            le90=round(le90_val, 2),
            le95=round(le95_val, 2),
            sample_count=n_valid,
            valid_pixel_count=n_valid,
            valid_pixel_pct=valid_pixel_pct,
            reference_min=round(float(np.min(ref_vals)), 2),
            reference_max=round(float(np.max(ref_vals)), 2),
            predicted_min=round(float(np.min(pred_vals)), 2),
            predicted_max=round(float(np.max(pred_vals)), 2),
            abs_rel=round(abs_rel, 4) if abs_rel is not None else None,
            sq_rel=round(sq_rel, 4) if sq_rel is not None else None,
            delta1=round(delta1, 2) if delta1 is not None else None,
            delta2=round(delta2, 2) if delta2 is not None else None,
            delta3=round(delta3, 2) if delta3 is not None else None,
            slope_mae=round(slope_mae, 2) if slope_mae is not None else None,
            slope_rmse=round(slope_rmse, 2) if slope_rmse is not None else None
        )

        # Determine active metrics and profile name
        prof_name = profile if profile in EvaluationService.METRIC_PROFILES else "terrain_standard"
        if selected_metrics and len(selected_metrics) > 0:
            active_metrics = selected_metrics
            if prof_name != "custom" and set(active_metrics) != set(EvaluationService.METRIC_PROFILES.get(prof_name, [])):
                prof_name = "custom"
        else:
            active_metrics = EvaluationService.METRIC_PROFILES.get(prof_name, EvaluationService.METRIC_PROFILES["terrain_standard"])

        # 4. Signed Error Map raster & image (coolwarm colormap)
        error_raster = np.full(predicted_dsm.shape, np.nan, dtype=np.float32)
        error_raster[valid] = (predicted_dsm[valid] - ref_aligned[valid]).astype(np.float32)

        abs_limit = max(1.0, float(np.percentile(np.abs(errors), 98)))
        norm_err = np.clip((error_raster + abs_limit) / (2.0 * abs_limit), 0.0, 1.0)

        error_colored = cm.coolwarm(norm_err)[:, :, :3]
        error_colored[~valid] = [0.06, 0.08, 0.12]  # dark background for invalid
        error_png_data = (error_colored * 255.0).astype(np.uint8)

        error_map_path = output_prefix.with_name(f"{output_prefix.stem}_error_map.png")
        Image.fromarray(error_png_data).save(error_map_path)

        # 5. Absolute Error Map image (magma colormap)
        abs_error_raster = np.full(predicted_dsm.shape, np.nan, dtype=np.float32)
        abs_error_raster[valid] = np.abs(predicted_dsm[valid] - ref_aligned[valid]).astype(np.float32)
        norm_abs = np.clip(abs_error_raster / abs_limit, 0.0, 1.0)
        abs_colored = cm.magma(norm_abs)[:, :, :3]
        abs_colored[~valid] = [0.04, 0.05, 0.08]
        abs_png_data = (abs_colored * 255.0).astype(np.uint8)

        abs_error_map_path = output_prefix.with_name(f"{output_prefix.stem}_abs_error_map.png")
        Image.fromarray(abs_png_data).save(abs_error_map_path)

        # 6. Predicted Height Map & Reference Height Map images (matching hypsometric terrain colormap)
        min_elev = min(float(np.min(pred_vals)), float(np.min(ref_vals)))
        max_elev = max(float(np.max(pred_vals)), float(np.max(ref_vals)))
        elev_range = max(1e-5, max_elev - min_elev)

        pred_raster = np.full(predicted_dsm.shape, np.nan, dtype=np.float32)
        pred_raster[valid] = predicted_dsm[valid].astype(np.float32)
        norm_pred = np.clip((pred_raster - min_elev) / elev_range, 0.0, 1.0)
        pred_colored = cm.terrain(norm_pred)[:, :, :3]
        pred_colored[~valid] = [0.06, 0.08, 0.12]
        pred_png_data = (pred_colored * 255.0).astype(np.uint8)
        pred_map_path = output_prefix.with_name(f"{output_prefix.stem}_pred_map.png")
        Image.fromarray(pred_png_data).save(pred_map_path)

        ref_raster = np.full(ref_aligned.shape, np.nan, dtype=np.float32)
        ref_raster[valid] = ref_aligned[valid].astype(np.float32)
        norm_ref = np.clip((ref_raster - min_elev) / elev_range, 0.0, 1.0)
        ref_colored = cm.terrain(norm_ref)[:, :, :3]
        ref_colored[~valid] = [0.06, 0.08, 0.12]
        ref_png_data = (ref_colored * 255.0).astype(np.uint8)
        ref_map_path = output_prefix.with_name(f"{output_prefix.stem}_ref_map.png")
        Image.fromarray(ref_png_data).save(ref_map_path)

        # 7. Save GeoTIFF error rasters if rasterio available
        try:
            import rasterio
            from rasterio.crs import CRS
            from affine import Affine
            gtiff_profile = {
                "driver": "GTiff",
                "height": predicted_dsm.shape[0],
                "width": predicted_dsm.shape[1],
                "count": 1,
                "dtype": "float32",
                "nodata": -9999.0
            }
            if crs:
                gtiff_profile["crs"] = CRS.from_user_input(crs)
            if transform:
                if isinstance(transform, (list, tuple)):
                    gtiff_profile["transform"] = Affine(*transform)
                else:
                    gtiff_profile["transform"] = transform

            err_gtiff_path = output_prefix.with_name(f"{output_prefix.stem}_error_map.tif")
            with rasterio.open(err_gtiff_path, "w", **gtiff_profile) as dst:
                e_out = error_raster.copy()
                e_out[~valid] = -9999.0
                dst.write(e_out.astype(np.float32), 1)

            abs_gtiff_path = output_prefix.with_name(f"{output_prefix.stem}_abs_error_map.tif")
            with rasterio.open(abs_gtiff_path, "w", **gtiff_profile) as dst:
                a_out = abs_error_raster.copy()
                a_out[~valid] = -9999.0
                dst.write(a_out.astype(np.float32), 1)
        except Exception as e:
            logger.debug(f"GeoTIFF export skipped or failed: {e}")

        # 8. Error Histogram (20 bins)
        clipped_errors = np.clip(errors, -abs_limit, abs_limit)
        counts, bin_edges = np.histogram(clipped_errors, bins=20, range=(-abs_limit, abs_limit))
        histogram_data = []
        for i in range(len(counts)):
            histogram_data.append({
                "bin_start": round(float(bin_edges[i]), 1),
                "bin_end": round(float(bin_edges[i+1]), 1),
                "bin_label": f"{bin_edges[i]:.1f} to {bin_edges[i+1]:.1f}m",
                "count": int(counts[i]),
                "percentage": round(float(counts[i] / n_valid * 100.0), 1)
            })

        # 9. Subsampled Scatter Points (up to 200 points for clear responsive plotting)
        sample_size = min(200, n_valid)
        rng = np.random.default_rng(42)
        sample_indices = rng.choice(n_valid, sample_size, replace=False)
        scatter_points = [
            {
                "reference": round(float(ref_vals[idx]), 1),
                "predicted": round(float(pred_vals[idx]), 1),
                "error": round(float(errors[idx]), 1)
            }
            for idx in sample_indices
        ]

        # 10. Scene Stratification (Urban, Sparse, Hilly, Forest)
        category_masks: Dict[str, np.ndarray] = {}
        source = "dataset_label"

        if strata_labels is not None:
            if isinstance(strata_labels, dict):
                for cat_name, c_mask in strata_labels.items():
                    if isinstance(c_mask, np.ndarray):
                        if c_mask.shape != predicted_dsm.shape:
                            c_mask_aligned = cv2.resize(
                                c_mask.astype(np.uint8),
                                (predicted_dsm.shape[1], predicted_dsm.shape[0]),
                                interpolation=cv2.INTER_NEAREST
                            ).astype(bool)
                        else:
                            c_mask_aligned = c_mask.astype(bool)
                        category_masks[str(cat_name)] = c_mask_aligned[valid]
            elif isinstance(strata_labels, np.ndarray):
                if strata_labels.shape != predicted_dsm.shape:
                    s_aligned = cv2.resize(
                        strata_labels,
                        (predicted_dsm.shape[1], predicted_dsm.shape[0]),
                        interpolation=cv2.INTER_NEAREST
                    )
                else:
                    s_aligned = strata_labels
                s_valid = s_aligned[valid]
                target_categories = ["Urban", "Sparse", "Hilly", "Forest"]
                for cat in target_categories:
                    cat_mask = (s_valid == cat)
                    if np.any(cat_mask):
                        category_masks[cat] = cat_mask
                for u_label in np.unique(s_valid):
                    u_str = str(u_label)
                    if u_str not in target_categories and u_str not in ["", "none", "nan", "0"]:
                        category_masks[u_str] = (s_valid == u_label)
        else:
            # When dataset labels are not present, categorize by reference slope regimes:
            # Urban (<10°), Sparse (10°–25°), Hilly (25°–40°), Forest (>40°)
            source = "topographic_slope"
            ref_slope = ref_slope_grid[valid]
            slope_strata = [
                ("Urban / Flat (<10°)", ref_slope < 10.0),
                ("Sparse / Undulating (10°–25°)", (ref_slope >= 10.0) & (ref_slope <= 25.0)),
                ("Hilly / Mountainous (25°–40°)", (ref_slope > 25.0) & (ref_slope <= 40.0)),
                ("Forest / Rugged (>40°)", ref_slope > 40.0)
            ]
            for s_name, s_m in slope_strata:
                category_masks[s_name] = s_m

        landscape_results: List[LandscapeMetric] = []
        for l_name, l_mask in category_masks.items():
            n_l = int(np.count_nonzero(l_mask))
            # Strictly omit categories without sufficient real samples (never fabricate categories)
            if n_l >= 10:
                l_preds = pred_vals[l_mask]
                l_refs = ref_vals[l_mask]
                l_diff = l_preds - l_refs
                l_abs_diff = np.abs(l_diff)
                l_mae = float(np.mean(l_abs_diff))
                l_rmse = float(np.sqrt(np.mean(l_diff ** 2)))
                l_bias = float(np.mean(l_diff))
                l_med_ae = float(np.median(l_abs_diff))
                try:
                    l_r, _ = pearsonr(l_preds, l_refs)
                    l_r = float(l_r) if np.isfinite(l_r) else 0.0
                except Exception:
                    l_r = 0.0
                landscape_results.append(LandscapeMetric(
                    landscape_type=l_name,
                    sample_count=n_l,
                    mae=round(l_mae, 2),
                    rmse=round(l_rmse, 2),
                    pearson_r=round(l_r, 3),
                    bias=round(l_bias, 2),
                    median_abs_error=round(l_med_ae, 2),
                    category_source=source
                ))

        return (
            metrics,
            error_map_path,
            abs_error_map_path,
            pred_map_path,
            ref_map_path,
            histogram_data,
            scatter_points,
            landscape_results,
            active_metrics,
            prof_name
        )
