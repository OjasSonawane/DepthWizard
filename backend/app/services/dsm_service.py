import logging
from pathlib import Path
from typing import Tuple, Dict, Any, Optional, List
import numpy as np
import cv2
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.cm as cm

from app.schemas.schemas import DSMStats, DisasterRiskStats

logger = logging.getLogger("depthwizard.dsm")

class DSMService:
    @staticmethod
    def compute_riley_tri(dsm: np.ndarray) -> np.ndarray:
        """
        Computes Terrain Ruggedness Index (TRI) following Riley, DeGloria, and Elliot (1999).
        TRI = sqrt( sum_{i=1..8} (z_i - z_0)^2 ) for each 3x3 neighborhood.
        """
        if dsm.ndim != 2:
            raise ValueError(f"Expected 2D elevation grid, got shape {dsm.shape}")

        h, w = dsm.shape
        padded = np.pad(dsm, 1, mode='edge')
        center = padded[1:-1, 1:-1]
        sum_sq_diff = np.zeros_like(dsm, dtype=np.float32)

        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                neighbor = padded[1 + dy:h + 1 + dy, 1 + dx:w + 1 + dx]
                diff = neighbor - center
                sum_sq_diff += (diff * diff).astype(np.float32)

        return np.sqrt(sum_sq_diff).astype(np.float32)

    @staticmethod
    def compute_slope_and_hillshade(
        dsm: np.ndarray,
        resolution: Optional[Tuple[float, float]] = None,
        sun_azimuth_deg: float = 315.0,
        sun_altitude_deg: float = 45.0
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Computes gradient-based slope (degrees) and analytical hillshade from DSM raster.
        Uses Horn's 3x3 finite-difference algorithm.
        Resolution should be provided in ground meters (cell_x, cell_y).
        """
        cell_x = abs(float(resolution[0])) if resolution and resolution[0] > 0 else 1.0
        cell_y = abs(float(resolution[1])) if resolution and resolution[1] > 0 else 1.0

        # Create clean float32 copy handling NaNs
        valid_mask = np.isfinite(dsm) & (dsm > -9000.0)
        clean_dsm = np.where(valid_mask, dsm, np.nanmean(dsm[valid_mask]) if np.any(valid_mask) else 0.0).astype(np.float32)

        # Compute directional gradients via Sobel / Horn
        # OpenCV Sobel: ksize=3 uses Horn's kernel weights [-1, 0, 1] and [1, 2, 1]
        dx = cv2.Sobel(clean_dsm, cv2.CV_32F, 1, 0, ksize=3) / (8.0 * cell_x)
        dy = cv2.Sobel(clean_dsm, cv2.CV_32F, 0, 1, ksize=3) / (8.0 * cell_y)

        # Slope in radians and degrees
        slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
        slope_deg = np.degrees(slope_rad)
        slope_deg = np.clip(slope_deg, 0.0, 90.0)

        # Set invalid pixels to NaN
        slope_deg[~valid_mask] = np.nan

        # Aspect in radians (mathematical counter-clockwise from East)
        aspect_rad = np.arctan2(-dy, dx)

        # Hillshade calculation
        zenith_rad = np.radians(90.0 - sun_altitude_deg)
        azimuth_math = np.radians(360.0 - sun_azimuth_deg + 90.0)

        hillshade = 255.0 * (
            (np.cos(zenith_rad) * np.cos(slope_rad)) +
            (np.sin(zenith_rad) * np.sin(slope_rad) * np.cos(azimuth_math - aspect_rad))
        )
        hillshade = np.clip(hillshade, 0.0, 255.0).astype(np.uint8)
        hillshade[~valid_mask] = 0

        return slope_deg.astype(np.float32), hillshade

    @staticmethod
    def compute_dsm_stats(
        dsm: np.ndarray,
        slope_deg: np.ndarray,
        crs_str: Optional[str] = None,
        is_metric: bool = True
    ) -> Tuple[DSMStats, DisasterRiskStats, List[Dict[str, Any]]]:
        """
        Calculates scientific terrain statistics, slope screening categories, and elevation histogram.
        Uses Riley et al. (1999) Terrain Ruggedness Index (TRI).
        """
        valid_mask = np.isfinite(dsm) & (dsm > -9000.0)
        valid_elev = dsm[valid_mask]

        if len(valid_elev) == 0:
            elev_min = elev_max = elev_mean = elev_median = elev_std = 0.0
        else:
            elev_min = float(np.min(valid_elev))
            elev_max = float(np.max(valid_elev))
            elev_mean = float(np.mean(valid_elev))
            elev_median = float(np.median(valid_elev))
            elev_std = float(np.std(valid_elev))

        relief = elev_max - elev_min

        # Slope statistics & screening thresholds: <15°, 15-30°, >30°
        valid_slope = slope_deg[np.isfinite(slope_deg)]
        n_slope = len(valid_slope)
        avg_slope = float(np.mean(valid_slope)) if n_slope > 0 else 0.0
        max_slope = float(np.max(valid_slope)) if n_slope > 0 else 0.0

        gentle_pct = float(np.count_nonzero(valid_slope < 15.0) / n_slope * 100.0) if n_slope > 0 else 0.0
        moderate_pct = float(np.count_nonzero((valid_slope >= 15.0) & (valid_slope <= 30.0)) / n_slope * 100.0) if n_slope > 0 else 0.0
        steep_pct = float(np.count_nonzero(valid_slope > 30.0) / n_slope * 100.0) if n_slope > 0 else 0.0

        dsm_stats = DSMStats(
            min_elevation=round(elev_min, 2),
            max_elevation=round(elev_max, 2),
            mean_elevation=round(elev_mean, 2),
            median_elevation=round(elev_median, 2),
            std_elevation=round(elev_std, 2),
            relief=round(relief, 2),
            average_slope_deg=round(avg_slope, 2),
            max_slope_deg=round(max_slope, 2),
            steep_area_pct=round(steep_pct, 2),
            crs=crs_str,
            is_metric=is_metric
        )

        # Disaster risk metrics
        low_thresh = elev_min + relief * 0.15
        low_lying_pct = float(np.count_nonzero(valid_elev <= low_thresh) / len(valid_elev) * 100.0) if len(valid_elev) > 0 else 0.0

        # Authentic Riley et al. (1999) Terrain Ruggedness Index
        tri_map = DSMService.compute_riley_tri(dsm)
        tri = float(np.mean(tri_map[valid_mask])) if np.count_nonzero(valid_mask) > 0 else 0.0

        risk_stats = DisasterRiskStats(
            low_lying_area_pct=round(low_lying_pct, 2),
            steep_slope_hazard_pct=round(steep_pct, 2),
            moderate_slope_pct=round(moderate_pct, 2),
            gentle_slope_pct=round(gentle_pct, 2),
            ruggedness_index=round(tri, 2),
            elevation_thresholds={
                "flood_risk_low_m": round(low_thresh, 2),
                "median_elevation_m": round(elev_median, 2),
                "high_ridge_m": round(elev_min + relief * 0.85, 2)
            }
        )

        # Elevation Histogram (20 bins)
        hist_data = []
        if len(valid_elev) > 0:
            counts, bin_edges = np.histogram(valid_elev, bins=20)
            for i in range(len(counts)):
                hist_data.append({
                    "bin_start": round(float(bin_edges[i]), 1),
                    "bin_end": round(float(bin_edges[i+1]), 1),
                    "bin_label": f"{bin_edges[i]:.0f}–{bin_edges[i+1]:.0f}{'m' if is_metric else ''}",
                    "count": int(counts[i]),
                    "percentage": round(float(counts[i] / len(valid_elev) * 100.0), 1)
                })

        return dsm_stats, risk_stats, hist_data

    @staticmethod
    def render_colorized_maps(
        dsm: np.ndarray,
        relative_depth: np.ndarray,
        slope_deg: np.ndarray,
        hillshade: np.ndarray,
        output_prefix: Path
    ) -> Dict[str, Path]:
        """
        Renders and exports presentation-grade colorized maps:
        - Grayscale depth
        - Turbo colorized depth
        - Terrain colorized elevation DSM
        - Hillshade PNG
        - Slope hazard heatmap PNG
        - Topographic contour overlay PNG
        """
        outputs = {}

        # 1. Grayscale depth PNG (0..255)
        depth_gray = (np.clip(relative_depth, 0.0, 1.0) * 255.0).astype(np.uint8)
        gray_path = output_prefix.with_name(f"{output_prefix.stem}_depth_gray.png")
        Image.fromarray(depth_gray).save(gray_path)
        outputs["depth_gray"] = gray_path

        # 2. Colorized depth map (Turbo colormap)
        depth_turbo = cm.turbo(relative_depth)[:, :, :3]
        depth_turbo = (depth_turbo * 255.0).astype(np.uint8)
        turbo_path = output_prefix.with_name(f"{output_prefix.stem}_depth_color.png")
        Image.fromarray(depth_turbo).save(turbo_path)
        outputs["depth_color"] = turbo_path

        # 3. Terrain colorized DSM (combining hillshade and colormap)
        dsm_valid = np.nan_to_num(dsm, nan=float(np.nanmin(dsm)))
        dsm_norm = (dsm_valid - np.min(dsm_valid)) / max(1e-5, (np.max(dsm_valid) - np.min(dsm_valid)))
        terrain_color = cm.terrain(dsm_norm)[:, :, :3]
        terrain_color = (terrain_color * 255.0).astype(np.uint8)

        # Blend with hillshade for photorealistic relief
        hs_3ch = np.dstack([hillshade, hillshade, hillshade]) / 255.0
        blended = (terrain_color * hs_3ch).astype(np.uint8)
        dsm_color_path = output_prefix.with_name(f"{output_prefix.stem}_dsm_color.png")
        Image.fromarray(blended).save(dsm_color_path)
        outputs["dsm_color"] = dsm_color_path

        # 4. Hillshade PNG
        hs_path = output_prefix.with_name(f"{output_prefix.stem}_hillshade.png")
        Image.fromarray(hillshade).save(hs_path)
        outputs["hillshade"] = hs_path

        # 5. Slope Hazard PNG (Inferno colormap)
        slope_norm = np.clip(slope_deg / 45.0, 0.0, 1.0)
        slope_color = cm.inferno(slope_norm)[:, :, :3]
        slope_color = (slope_color * 255.0).astype(np.uint8)
        slope_path = output_prefix.with_name(f"{output_prefix.stem}_slope.png")
        Image.fromarray(slope_color).save(slope_path)
        outputs["slope"] = slope_path

        # 6. Contour Map overlay
        contour_path = output_prefix.with_name(f"{output_prefix.stem}_contour.png")
        fig, ax = plt.subplots(figsize=(8, 8), dpi=150)
        ax.axis('off')
        fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
        levels = 15
        ax.contour(dsm_norm, levels=levels, cmap='coolwarm', linewidths=0.8)
        plt.savefig(contour_path, bbox_inches='tight', pad_inches=0, transparent=True)
        plt.close(fig)
        outputs["contour"] = contour_path

        return outputs
