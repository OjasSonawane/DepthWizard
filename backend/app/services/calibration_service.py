import logging
from abc import ABC, abstractmethod
from typing import Tuple, Optional, List, Dict, Any
import numpy as np
import rasterio
from sklearn.linear_model import HuberRegressor, LinearRegression
from sklearn.metrics import r2_score
from scipy.stats import pearsonr, spearmanr

from app.schemas.schemas import CalibrationResult, GCPItem
from app.services.geospatial_service import GeospatialService

logger = logging.getLogger("depthwizard.calibration")


class BaseCalibrationStrategy(ABC):
    """
    Abstract Strategy for converting relative disparity surfaces into calibrated elevations.
    Enforces strict mathematical computation with zero fabricated constants.
    """
    @abstractmethod
    def calibrate(
        self,
        relative_depth: np.ndarray,
        **kwargs
    ) -> Tuple[np.ndarray, CalibrationResult]:
        pass


class RelativeCalibrationStrategy(BaseCalibrationStrategy):
    """
    Calibrates non-georeferenced imagery into a Relative Digital Surface Model (rDSM).
    Normalized to [0.0, 100.0] relative relief units, strictly flagged as non-metric.
    """
    def calibrate(
        self,
        relative_depth: np.ndarray,
        **kwargs
    ) -> Tuple[np.ndarray, CalibrationResult]:
        valid_mask = np.isfinite(relative_depth)
        if not np.any(valid_mask):
            raise ValueError("Input depth raster contains no finite valid pixels.")

        d_min = float(np.min(relative_depth[valid_mask]))
        d_max = float(np.max(relative_depth[valid_mask]))
        relief = d_max - d_min

        if relief > 1e-6:
            norm = (relative_depth - d_min) / relief
            confidence = "relative"
            msg = "Non-georeferenced imagery: produced relative digital surface model (rDSM) scaled [0–100%]."
        else:
            norm = np.zeros_like(relative_depth)
            confidence = "degenerate"
            msg = "Degenerate depth surface: input has zero relief (constant depth). Generated flat rDSM."

        rdsm = (norm * 100.0).astype(np.float32)

        result = CalibrationResult(
            method="relative",
            is_metric=False,
            scale=100.0 if relief > 1e-6 else 0.0,
            offset=0.0,
            r2=None,
            rmse=None,
            mae=None,
            correlation=None,
            valid_pixels=int(np.count_nonzero(valid_mask)),
            gcp_count=None,
            confidence=confidence,
            message=msg
        )
        return rdsm, result


class DEMCalibrationStrategy(BaseCalibrationStrategy):
    """
    Metric scale calibration against a co-registered reference DEM (e.g. SRTM/CartoDEM)
    using robust Huber regression: Z(x, y) = a * d(x, y) + b.
    Detects disparity polarity, rejects outliers, and computes genuine goodness-of-fit statistics.
    """
    def calibrate(
        self,
        relative_depth: np.ndarray,
        reference_dem: Optional[np.ndarray] = None,
        **kwargs
    ) -> Tuple[np.ndarray, CalibrationResult]:
        if reference_dem is None:
            raise ValueError("Reference DEM raster is required for DEM calibration.")

        if relative_depth.shape != reference_dem.shape:
            raise ValueError(
                f"Dimension mismatch: relative depth {relative_depth.shape} != reference DEM {reference_dem.shape}."
            )

        valid_mask = (
            np.isfinite(relative_depth) &
            np.isfinite(reference_dem) &
            (reference_dem > -9000.0)
        )
        n_valid = int(np.count_nonzero(valid_mask))
        if n_valid < 20:
            raise ValueError(
                f"Insufficient valid overlapping pixels ({n_valid} found, minimum 20 required) between relative depth and reference DEM."
            )

        x_raw = relative_depth[valid_mask].astype(np.float64)
        y_raw = reference_dem[valid_mask].astype(np.float64)

        # Check empirical monotonic correlation between disparity and reference elevation via Spearman rank correlation
        rng = np.random.RandomState(42)
        check_idx = rng.choice(len(x_raw), min(2000, len(x_raw)), replace=False) if len(x_raw) > 2000 else slice(None)
        r_emp, _ = spearmanr(x_raw[check_idx], y_raw[check_idx])
        inverted_polarity = False
        if np.isfinite(r_emp) and r_emp < 0.0:
            # Model disparity polarity is inverted (smaller disparity = higher elevation)
            x_raw = 1.0 - x_raw
            inverted_polarity = True
            logger.info("Disparity polarity inversion detected and compensated for calibration.")

        # Subsample for robust Huber regression if pixel count is huge
        if len(x_raw) > 50000:
            idx = rng.choice(len(x_raw), 50000, replace=False)
            x_sample = x_raw[idx].reshape(-1, 1)
            y_sample = y_raw[idx]
        else:
            x_sample = x_raw.reshape(-1, 1)
            y_sample = y_raw

        try:
            reg = HuberRegressor(epsilon=1.35, max_iter=300)
            reg.fit(x_sample, y_sample)
            scale = float(reg.coef_[0])
            offset = float(reg.intercept_)
        except Exception as e:
            logger.warning(f"Huber regression failed ({e}); falling back to Ordinary Least Squares.")
            reg = LinearRegression()
            reg.fit(x_sample, y_sample)
            scale = float(reg.coef_[0])
            offset = float(reg.intercept_)

        if scale <= 0.0:
            # Regression indicates inverse relationship; invert polarity and re-fit
            logger.info("Negative regression slope detected; inverting disparity polarity and refitting.")
            inverted_polarity = not inverted_polarity
            x_sample = 1.0 - x_sample
            try:
                reg = HuberRegressor(epsilon=1.35, max_iter=300)
                reg.fit(x_sample, y_sample)
            except Exception:
                reg = LinearRegression()
                reg.fit(x_sample, y_sample)
            scale = float(reg.coef_[0])
            offset = float(reg.intercept_)

        if scale <= 0.0:
            raise ValueError(
                f"Calibrated scale factor is non-positive (scale={scale:.4f}). "
                "The neural depth geometry does not exhibit positive topographic correlation with the reference elevation."
            )

        adjusted_depth = (1.0 - relative_depth) if inverted_polarity else relative_depth
        dsm = (adjusted_depth * scale + offset).astype(np.float32)

        # Compute empirical fit statistics over the evaluated sample
        preds = reg.predict(x_sample)
        residuals = y_sample - preds
        r2 = float(r2_score(y_sample, preds))
        rmse = float(np.sqrt(np.mean(residuals ** 2)))
        mae = float(np.mean(np.abs(residuals)))
        try:
            r_val, _ = pearsonr(x_sample.ravel(), y_sample.ravel())
            correlation = float(r_val) if np.isfinite(r_val) else 0.0
        except Exception:
            correlation = None

        confidence = "high" if (r2 >= 0.50 and n_valid >= 100) else "medium" if (r2 >= 0.05 or (correlation is not None and correlation >= 0.10) or n_valid >= 1000) else "low"
        polarity_msg = " [inverted polarity compensated]" if inverted_polarity else ""
        msg = f"Calibrated via reference DEM{polarity_msg} (R²={r2:.2f}, RMSE={rmse:.2f}m, MAE={mae:.2f}m, N={n_valid})."

        result = CalibrationResult(
            method="dem",
            is_metric=True,
            scale=round(scale, 4),
            offset=round(offset, 4),
            r2=round(max(0.0, r2), 4),
            rmse=round(rmse, 3),
            mae=round(mae, 3),
            correlation=round(correlation, 3) if correlation is not None else None,
            valid_pixels=n_valid,
            gcp_count=None,
            confidence=confidence,
            message=msg
        )
        return dsm, result


class GCPCalibrationStrategy(BaseCalibrationStrategy):
    """
    Metric scale calibration against surveyed Ground Control Points (GCPs).
    Automatically reprojects geodetic coordinates (WGS84 lon/lat) to the raster's projected CRS,
    samples depth at pixel coordinates, and performs least-squares regression.
    """
    def calibrate(
        self,
        relative_depth: np.ndarray,
        gcps: Optional[List[GCPItem]] = None,
        transform_list: Optional[List[float]] = None,
        crs_str: Optional[str] = None,
        **kwargs
    ) -> Tuple[np.ndarray, CalibrationResult]:
        if not gcps or len(gcps) < 3:
            raise ValueError("At least 3 Ground Control Points (GCPs) are required for affine calibration.")

        h, w = relative_depth.shape
        x_depth: List[float] = []
        y_elev: List[float] = []

        for gcp in gcps:
            gcp_x, gcp_y = float(gcp.x), float(gcp.y)

            if transform_list:
                from rasterio.transform import Affine
                # Reproject geodetic coordinates to projected CRS if needed
                if crs_str and abs(gcp_x) <= 180.0 and abs(gcp_y) <= 90.0:
                    try:
                        crs = rasterio.crs.CRS.from_string(crs_str)
                        if not crs.is_geographic:
                            gcp_x, gcp_y = GeospatialService.reproject_coords(
                                gcp_x, gcp_y, "EPSG:4326", crs_str
                            )
                    except Exception as ex:
                        logger.debug(f"GCP coordinate reprojection note: {ex}")

                t = Affine(*transform_list)
                inv_t = ~t
                col, row = inv_t * (gcp_x, gcp_y) if not hasattr(inv_t, '__matmul__') else inv_t @ (gcp_x, gcp_y)
                row, col = int(round(row)), int(round(col))
            else:
                col, row = int(round(gcp_x)), int(round(gcp_y))

            if 0 <= row < h and 0 <= col < w:
                val = float(relative_depth[row, col])
                elev = float(gcp.elevation)
                if np.isfinite(val) and np.isfinite(elev) and -500.0 <= elev <= 10000.0:
                    x_depth.append(val)
                    y_elev.append(elev)
                elif np.isfinite(val):
                    logger.warning(f"GCP {gcp.id} has unphysical elevation {elev}m (terrestrial range [-500m, 10000m]); rejected.")

        if len(x_depth) < 3:
            raise ValueError(
                f"Only {len(x_depth)} GCPs fell inside image bounds with finite terrestrial elevations (minimum 3 required)."
            )

        x_arr = np.array(x_depth, dtype=np.float64)
        y_arr = np.array(y_elev, dtype=np.float64)

        # Polarity check via Spearman rank correlation
        r_emp, _ = spearmanr(x_arr, y_arr) if len(x_arr) >= 3 else (1.0, 0.0)
        inverted_polarity = False
        if np.isfinite(r_emp) and r_emp < 0.0:
            x_arr = 1.0 - x_arr
            inverted_polarity = True

        reg = LinearRegression()
        reg.fit(x_arr.reshape(-1, 1), y_arr)
        scale = float(reg.coef_[0])
        offset = float(reg.intercept_)

        if scale <= 0.0:
            raise ValueError(
                f"GCP calibration failed: fitted scale factor is non-positive (scale={scale:.4f}). "
                "Provided GCP elevations do not correspond to positive depth gradient."
            )

        adjusted_depth = (1.0 - relative_depth) if inverted_polarity else relative_depth
        dsm = (adjusted_depth * scale + offset).astype(np.float32)

        preds = reg.predict(x_arr.reshape(-1, 1))
        residuals = y_arr - preds
        r2 = float(r2_score(y_arr, preds)) if len(y_arr) > 2 else 1.0
        rmse = float(np.sqrt(np.mean(residuals ** 2)))
        mae = float(np.mean(np.abs(residuals)))
        try:
            r_val, _ = pearsonr(x_arr, y_arr)
            correlation = float(r_val) if np.isfinite(r_val) else 0.0
        except Exception:
            correlation = None

        confidence = "high" if (r2 >= 0.70 and len(x_depth) >= 5) else "medium"

        result = CalibrationResult(
            method="gcp",
            is_metric=True,
            scale=round(scale, 4),
            offset=round(offset, 4),
            r2=round(max(0.0, r2), 4),
            rmse=round(rmse, 3),
            mae=round(mae, 3),
            correlation=round(correlation, 3) if correlation is not None else None,
            valid_pixels=len(x_depth),
            gcp_count=len(x_depth),
            confidence=confidence,
            message=f"Calibrated with {len(x_depth)} GCPs (R²={r2:.2f}, Residual RMSE={rmse:.2f}m, MAE={mae:.2f}m)."
        )
        return dsm, result


class ScaledEstimateCalibrationStrategy(BaseCalibrationStrategy):
    """
    Transparent scaled estimate for georeferenced imagery when neither DEM nor GCPs are provided.
    Explicitly marked as an uncalibrated estimate (is_metric=False) with clear confidence flagging.
    """
    def calibrate(
        self,
        relative_depth: np.ndarray,
        estimated_relief_m: float = 60.0,
        base_elevation_m: float = 100.0,
        **kwargs
    ) -> Tuple[np.ndarray, CalibrationResult]:
        valid_mask = np.isfinite(relative_depth)
        if not np.any(valid_mask):
            raise ValueError("Input depth raster contains no finite valid pixels.")

        d_min = float(np.min(relative_depth[valid_mask]))
        d_max = float(np.max(relative_depth[valid_mask]))
        norm = (relative_depth - d_min) / max(1e-6, d_max - d_min)

        dsm = (norm * float(estimated_relief_m) + float(base_elevation_m)).astype(np.float32)

        result = CalibrationResult(
            method="scaled_estimate",
            is_metric=False,
            scale=float(estimated_relief_m),
            offset=float(base_elevation_m),
            r2=None,
            rmse=None,
            mae=None,
            correlation=None,
            valid_pixels=int(np.count_nonzero(valid_mask)),
            gcp_count=None,
            confidence="estimated",
            message="Uncalibrated georeferenced estimate: nominal relief applied. Reference DEM/GCP required for metric validity."
        )
        return dsm, result


class CalibrationService:
    """
    Unified Calibration Facade dispatching to strict mathematical strategies.
    """
    @staticmethod
    def calibrate_relative(relative_depth: np.ndarray) -> Tuple[np.ndarray, CalibrationResult]:
        return RelativeCalibrationStrategy().calibrate(relative_depth)

    @staticmethod
    def calibrate_scaled_estimate(
        relative_depth: np.ndarray,
        estimated_relief_m: float = 60.0,
        base_elevation_m: float = 100.0
    ) -> Tuple[np.ndarray, CalibrationResult]:
        return ScaledEstimateCalibrationStrategy().calibrate(
            relative_depth,
            estimated_relief_m=estimated_relief_m,
            base_elevation_m=base_elevation_m
        )

    @staticmethod
    def calibrate_with_dem(
        relative_depth: np.ndarray,
        reference_dem: np.ndarray
    ) -> Tuple[np.ndarray, CalibrationResult]:
        return DEMCalibrationStrategy().calibrate(
            relative_depth,
            reference_dem=reference_dem
        )

    @staticmethod
    def calibrate_with_gcps(
        relative_depth: np.ndarray,
        gcps: List[GCPItem],
        transform_list: Optional[List[float]] = None,
        crs_str: Optional[str] = None
    ) -> Tuple[np.ndarray, CalibrationResult]:
        return GCPCalibrationStrategy().calibrate(
            relative_depth,
            gcps=gcps,
            transform_list=transform_list,
            crs_str=crs_str
        )
