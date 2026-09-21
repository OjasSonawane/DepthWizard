from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.services.depth_service import PipelineManager
from app.schemas.schemas import ReconstructionSummary, ImageMetadata, DSMStats, MeshMetadata
from app.utils.security import validate_safe_id

router = APIRouter(prefix="", tags=["Visualization"])

@router.get("/results/{job_id}", response_model=ReconstructionSummary)
async def get_results(job_id: str):
    """
    Returns full reconstruction results summary for the given job.
    """
    job_id = validate_safe_id(job_id, "job_id")
    pipeline = PipelineManager.get_instance()
    try:
        return pipeline.get_results(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

@router.get("/results/{job_id}/depth")
async def get_depth_assets(job_id: str):
    """
    Returns relative depth visualization assets (grayscale, colorized, numerical stats).
    """
    job_id = validate_safe_id(job_id, "job_id")
    pipeline = PipelineManager.get_instance()
    try:
        results = pipeline.get_results(job_id)
        return {
            "job_id": job_id,
            "depth_gray": results.assets["depth_gray"],
            "depth_color": results.assets["depth_color"],
            "calibration": results.calibration,
            "device_used": results.device_used,
            "min_val": 0.0,
            "max_val": 1.0,
            "unit": "relative",
            "array_type": "float32",
            "dimensions": results.dimensions
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

@router.get("/results/{job_id}/dsm")
async def get_dsm_assets(job_id: str):
    """
    Returns DSM raster assets (colorized, hillshade, slope, contours, stats, elevation histogram).
    """
    job_id = validate_safe_id(job_id, "job_id")
    pipeline = PipelineManager.get_instance()
    try:
        results = pipeline.get_results(job_id)
        job = pipeline.jobs[job_id]
        return {
            "job_id": job_id,
            "dsm_geotiff": results.assets["dsm_geotiff"],
            "dsm_color": results.assets["dsm_color"],
            "hillshade": results.assets["hillshade"],
            "slope": results.assets["slope"],
            "contour": results.assets["contour"],
            "stats": results.dsm_stats,
            "elevation_histogram": job.get("elevation_histogram", []),
            "is_metric": results.dsm_stats.is_metric,
            "crs": results.image_metadata.crs,
            "resolution": results.image_metadata.resolution,
            "elevation_units": "meters (AMSL)" if results.dsm_stats.is_metric else "relative elevation units [0-100]"
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

@router.get("/results/{job_id}/validation")
async def get_validation_results(job_id: str):
    """
    Returns scientific accuracy validation result against reference elevation data.
    """
    job_id = validate_safe_id(job_id, "job_id")
    pipeline = PipelineManager.get_instance()
    try:
        return pipeline.get_evaluation(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

@router.get("/results/{job_id}/artifacts")
async def get_job_artifacts(job_id: str):
    """
    Returns all registered artifact URLs and assets for the job.
    """
    job_id = validate_safe_id(job_id, "job_id")
    pipeline = PipelineManager.get_instance()
    try:
        artifacts = pipeline.get_artifacts(job_id)
        return {
            "job_id": job_id,
            "artifacts": artifacts
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

@router.get("/results/{job_id}/mesh")
async def get_mesh_assets(job_id: str, quality: str = Query("high", pattern="^(low|medium|high)$")):
    """
    Returns 3D mesh assets with specified LOD quality (low: 64x64, medium: 128x128, high: 192x192).
    """
    job_id = validate_safe_id(job_id, "job_id")
    pipeline = PipelineManager.get_instance()
    try:
        results = pipeline.get_results(job_id)
        hf_url = f"/storage/meshes/{job_id}_{quality}_heightfield.json" if quality != "high" else f"/storage/meshes/{job_id}_heightfield.json"
        obj_url = f"/storage/meshes/{job_id}_{quality}_terrain.obj" if quality != "high" else f"/storage/meshes/{job_id}_terrain.obj"

        return {
            "job_id": job_id,
            "mesh_metadata": {
                **results.mesh_metadata.model_dump(),
                "heightfield_url": hf_url,
                "obj_url": obj_url,
                "quality": quality
            },
            "heightfield_url": hf_url,
            "obj_url": obj_url,
            "rgb_texture": results.assets["rgb_texture"]
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

@router.get("/results/{job_id}/metadata", response_model=ImageMetadata)
async def get_image_metadata(job_id: str):
    """
    Returns spatial metadata for the input image.
    """
    job_id = validate_safe_id(job_id, "job_id")
    pipeline = PipelineManager.get_instance()
    try:
        results = pipeline.get_results(job_id)
        return results.image_metadata
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

@router.get("/results/{job_id}/inspect-point")
async def inspect_point(
    job_id: str,
    x_pct: Optional[float] = Query(None, ge=0.0, le=1.0),
    y_pct: Optional[float] = Query(None, ge=0.0, le=1.0),
    pixel_x: Optional[int] = Query(None, ge=0),
    pixel_y: Optional[int] = Query(None, ge=0)
):
    """
    Returns real scientific elevations (predicted, reference if available, error if available),
    slope, and coordinates for a single queried terrain point.
    """
    job_id = validate_safe_id(job_id, "job_id")
    import numpy as np
    from pathlib import Path
    import rasterio
    from app.config import settings

    pipeline = PipelineManager.get_instance()
    try:
        results = pipeline.get_results(job_id)
        job = pipeline.jobs.get(job_id, {})

        dsm_path = settings.STORAGE_DIR / "dsm" / f"{job_id}_dsm.npy"
        if dsm_path.exists():
            dsm = np.load(dsm_path)
        else:
            tif_path = settings.STORAGE_DIR / "dsm" / f"{job_id}_dsm.tif"
            if not tif_path.exists():
                raise HTTPException(status_code=404, detail="DSM raster not found.")
            with rasterio.open(tif_path) as src:
                dsm = src.read(1)

        h, w = dsm.shape
        if pixel_x is not None and pixel_y is not None:
            px = int(np.clip(pixel_x, 0, w - 1))
            py = int(np.clip(pixel_y, 0, h - 1))
        elif x_pct is not None and y_pct is not None:
            px = int(np.clip(round(x_pct * (w - 1)), 0, w - 1))
            py = int(np.clip(round(y_pct * (h - 1)), 0, h - 1))
        else:
            raise HTTPException(status_code=400, detail="Must supply either (pixel_x, pixel_y) or (x_pct, y_pct)")

        pred_val = float(dsm[py, px])

        # Reference height if available
        ref_val = None
        error_val = None
        ref_file = job.get("ref_file_path") or job.get("dem_path")
        if ref_file and Path(ref_file).exists():
            try:
                import cv2
                from app.services.geospatial_service import GeospatialService
                meta = results.image_metadata
                ref_dsm = None
                if meta.crs and meta.transform:
                    try:
                        ref_dsm = GeospatialService.reproject_match(
                            reference_path=Path(ref_file),
                            target_shape=(h, w),
                            target_crs_str=meta.crs,
                            target_transform_list=meta.transform
                        )
                    except Exception:
                        ref_dsm = None
                if ref_dsm is None:
                    ref_p = Path(ref_file)
                    if ref_p.suffix.lower() == ".npy":
                        ref_dsm = np.load(ref_p).astype(np.float32)
                    elif ref_p.suffix.lower() in [".tif", ".tiff"]:
                        with rasterio.open(ref_p) as src:
                            ref_dsm = src.read(1).astype(np.float32)
                            nodata = src.nodata
                            if nodata is not None:
                                ref_dsm[ref_dsm == nodata] = np.nan
                    else:
                        from PIL import Image
                        with Image.open(ref_p) as pil_ref:
                            ref_dsm = np.array(pil_ref.convert("L"), dtype=np.float32)
                    if ref_dsm is not None and ref_dsm.shape != (h, w):
                        ref_dsm = cv2.resize(ref_dsm, (w, h), interpolation=cv2.INTER_LINEAR)

                if ref_dsm is not None:
                    r_val = float(ref_dsm[py, px])
                    if np.isfinite(r_val) and r_val > -9000.0:
                        ref_val = round(r_val, 2)
                        error_val = round(pred_val - r_val, 2)
            except Exception:
                ref_val = None
                error_val = None

        # Slope
        slope_path = settings.STORAGE_DIR / "dsm" / f"{job_id}_slope.npy"
        slope_deg = 0.0
        if slope_path.exists():
            slope_arr = np.load(slope_path)
            slope_deg = float(slope_arr[py, px])
        else:
            dx = abs(float(dsm[py, min(px + 1, w - 1)]) - float(dsm[py, max(px - 1, 0)]))
            dy = abs(float(dsm[min(py + 1, h - 1), px]) - float(dsm[max(py - 1, 0), px]))
            slope_deg = float(np.degrees(np.arctan(np.hypot(dx, dy) / 2.0)))

        # Geographic coordinates
        geo_coords = None
        meta = results.image_metadata
        if meta.bounds:
            west, south, east, north = meta.bounds
            easting = west + (px / max(w - 1, 1)) * (east - west)
            northing = north - (py / max(h - 1, 1)) * (north - south)
            geo_coords = {"x": round(easting, 2), "y": round(northing, 2)}
            if meta.crs and ("4326" in meta.crs or "WGS 84" in meta.crs):
                geo_coords["lon"] = round(easting, 6)
                geo_coords["lat"] = round(northing, 6)

        return {
            "job_id": job_id,
            "pixel_coords": {"x": px, "y": py},
            "geo_coords": geo_coords,
            "predicted_height": round(pred_val, 2),
            "reference_height": ref_val,
            "error": error_val,
            "slope_deg": round(slope_deg, 1),
            "is_metric": results.dsm_stats.is_metric,
            "unit": "meters" if results.dsm_stats.is_metric else "relative"
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to inspect point: {str(e)}")
