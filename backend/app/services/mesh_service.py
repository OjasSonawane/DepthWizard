import json
import logging
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
import numpy as np
import cv2

from app.schemas.schemas import MeshMetadata

logger = logging.getLogger("depthwizard.mesh")

QUALITY_GRID_MAP = {
    "low": 64,
    "medium": 128,
    "high": 192
}

class MeshService:
    @staticmethod
    def generate_mesh_assets(
        dsm: np.ndarray,
        output_prefix: Path,
        quality: str = "high",
        grid_dim: Optional[int] = None,
        exaggeration: float = 1.0,
        reference_dsm: Optional[np.ndarray] = None
    ) -> Tuple[MeshMetadata, Path, Path]:
        """
        Converts 2D DSM into:
        1. Compact JSON heightfield payload for high-performance Three.js custom buffer geometry.
        2. Standard Wavefront .OBJ 3D terrain model with UVs for GIS/CAD export.
        Supports multi-LOD qualities (low: 64x64, medium: 128x128, high: 192x192).
        """
        if dsm is None or not isinstance(dsm, np.ndarray):
            raise ValueError("Input DSM must be a valid 2D numpy array.")
        if dsm.ndim != 2:
            raise ValueError(f"Input DSM must be a 2D array, got {dsm.ndim} dimensions.")
        
        h_orig, w_orig = dsm.shape
        if h_orig < 2 or w_orig < 2:
            raise ValueError(f"Input DSM dimensions too small for 3D terrain mesh: ({h_orig}x{w_orig}). Minimum 2x2 required.")

        if not grid_dim:
            grid_dim = QUALITY_GRID_MAP.get(quality.lower(), 192)

        grid_w = max(2, grid_dim)
        aspect = max(0.01, min(100.0, float(h_orig) / float(w_orig)))
        grid_h = max(2, int(round(grid_w * aspect)))

        # Clean non-finite values and clamp extreme unphysical elevations (e.g. +-10^20)
        valid_mask = np.isfinite(dsm) & (dsm > -15000.0) & (dsm < 15000.0) & (dsm > -9000.0)
        min_val = float(np.min(dsm[valid_mask])) if np.any(valid_mask) else 0.0
        max_val = float(np.max(dsm[valid_mask])) if np.any(valid_mask) else 100.0
        dsm_clean = np.where(valid_mask, dsm, min_val)
        dsm_clean = np.clip(dsm_clean, -15000.0, 15000.0)

        # Select appropriate resampling method:
        # If decimation (grid smaller than DSM data): use INTER_AREA for area averaging.
        # If upsampling (grid larger than DSM data, e.g. low-res inputs): use INTER_CUBIC for continuous surface curvature!
        is_upsampling = bool(grid_w > w_orig or grid_h > h_orig)
        interp_mode = cv2.INTER_CUBIC if is_upsampling else cv2.INTER_AREA
        dsm_grid = cv2.resize(dsm_clean, (grid_w, grid_h), interpolation=interp_mode)

        # For very coarse input images (e.g. 16x10 or <64px), cubic upsampling of discrete steps
        # can still exhibit stepped artifacts. Apply a gentle spatial continuity filter to the RENDER heightfield only,
        # preserving the underlying DSM raster and true min/max bounds.
        if w_orig < 64 or h_orig < 64:
            ksize = 5 if grid_w >= 128 else 3
            dsm_grid = cv2.GaussianBlur(dsm_grid, (ksize, ksize), sigmaX=1.0, sigmaY=1.0)
            dsm_grid = np.clip(dsm_grid, min_val, max_val)

        world_x_span = 100.0
        world_z_span = round(100.0 * aspect, 4)

        relief = max(1e-5, max_val - min_val)
        # Base terrain height in WebGL units (exaggeration slider scales this in Three.js)
        base_scene_height = 18.0
        normalized_y = ((dsm_grid - min_val) / relief) * base_scene_height

        # Resample reference DSM if available for point inspection
        reference_elevations = None
        elevation_errors = None
        if reference_dsm is not None:
            try:
                ref_valid = np.isfinite(reference_dsm) & (reference_dsm > -9000.0)
                ref_clean = np.where(ref_valid, reference_dsm, np.nan)
                ref_grid = cv2.resize(ref_clean, (grid_w, grid_h), interpolation=cv2.INTER_NEAREST)

                ref_list = []
                err_list = []
                for r in range(grid_h):
                    for c in range(grid_w):
                        r_val = ref_grid[r, c]
                        if np.isfinite(r_val):
                            p_val = float(dsm_grid[r, c])
                            r_f = float(r_val)
                            ref_list.append(round(r_f, 2))
                            err_list.append(round(p_val - r_f, 2))
                        else:
                            ref_list.append(None)
                            err_list.append(None)
                reference_elevations = ref_list
                elevation_errors = err_list
            except Exception as e_ref:
                logger.warning(f"Could not compute reference elevation grid: {e_ref}")

        # 1. Heightfield JSON
        heightfield_data = {
            "quality": quality,
            "grid_width": grid_w,
            "grid_height": grid_h,
            "data_width": w_orig,
            "data_height": h_orig,
            "is_upsampled": is_upsampling,
            "interpolation_method": "bicubic" if is_upsampling else "area_decimation",
            "world_x_span": world_x_span,
            "world_z_span": world_z_span,
            "min_elevation": round(min_val, 2),
            "max_elevation": round(max_val, 2),
            "relief": round(relief, 2),
            "heights": np.round(normalized_y.flatten(), 3).tolist(),
            "raw_elevations": np.round(dsm_grid.flatten(), 2).tolist(),
            "reference_elevations": reference_elevations,
            "elevation_errors": elevation_errors
        }

        json_name = f"{output_prefix.stem}_{quality}_heightfield.json" if quality != "high" else f"{output_prefix.stem}_heightfield.json"
        json_path = output_prefix.with_name(json_name)
        with open(json_path, "w") as f:
            json.dump(heightfield_data, f)

        # 2. Wavefront OBJ export
        obj_name = f"{output_prefix.stem}_{quality}_terrain.obj" if quality != "high" else f"{output_prefix.stem}_terrain.obj"
        obj_path = output_prefix.with_name(obj_name)
        with open(obj_path, "w") as f:
            f.write("# DepthWizard 3D Terrain Model\n")
            f.write(f"# Quality: {quality} ({grid_w} x {grid_h})\n")
            
            denom_h = max(1, grid_h - 1)
            denom_w = max(1, grid_w - 1)
            for r in range(grid_h):
                z = (r / denom_h - 0.5) * world_z_span
                for c in range(grid_w):
                    x = (c / denom_w - 0.5) * world_x_span
                    y = float(normalized_y[r, c])
                    f.write(f"v {x:.4f} {y:.4f} {z:.4f}\n")

            for r in range(grid_h):
                v = 1.0 - (r / denom_h)
                for c in range(grid_w):
                    u = c / denom_w
                    f.write(f"vt {u:.4f} {v:.4f}\n")

            for r in range(grid_h - 1):
                for c in range(grid_w - 1):
                    i1 = r * grid_w + c + 1
                    i2 = r * grid_w + (c + 1) + 1
                    i3 = (r + 1) * grid_w + (c + 1) + 1
                    i4 = (r + 1) * grid_w + c + 1
                    f.write(f"f {i1}/{i1} {i2}/{i2} {i3}/{i3}\n")
                    f.write(f"f {i1}/{i1} {i3}/{i3} {i4}/{i4}\n")

        vertex_count = grid_w * grid_h
        face_count = (grid_w - 1) * (grid_h - 1) * 2

        meta = MeshMetadata(
            grid_width=grid_w,
            grid_height=grid_h,
            vertex_count=vertex_count,
            face_count=face_count,
            heightfield_url="",
            obj_url="",
            quality=quality
        )

        return meta, json_path, obj_path
