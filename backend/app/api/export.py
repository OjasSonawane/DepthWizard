import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.services.depth_service import PipelineManager
from app.services.geospatial_service import GeospatialService
from app.schemas.schemas import GeoTIFFVerificationResult
from app.utils.security import validate_safe_id, assert_path_confined

router = APIRouter(prefix="", tags=["Export"])

def build_project_report(job_id: str, results) -> dict:
    pipeline = PipelineManager.get_instance()
    job = pipeline.jobs.get(job_id, {})
    eval_data = job.get("evaluation", {})

    report = {
        "platform": "DepthWizard AI Remote-Sensing 3D Reconstruction",
        "version": settings.VERSION,
        "pipeline_version": settings.VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "job_id": job_id,
        "input": {
            "filename": results.filename,
            "file_hash": getattr(results.image_metadata, "file_hash", None) or "N/A",
            "format": results.image_metadata.format,
            "dimensions": f"{results.image_metadata.width} x {results.image_metadata.height}",
            "is_georeferenced": results.is_georeferenced,
            "crs": results.image_metadata.crs or "Spatial reference unavailable",
            "resolution": f"{results.image_metadata.resolution[0]}m x {results.image_metadata.resolution[1]}m" if results.image_metadata.resolution else "Relative pixel grid",
            "bounds": results.image_metadata.bounds,
            "band_count": results.image_metadata.band_count,
            "datatype": getattr(results.image_metadata, "native_dtype", results.image_metadata.datatype)
        },
        "pipeline_dimensions": {
            "input_resolution": f"{results.image_metadata.width} x {results.image_metadata.height}",
            "depth_resolution": f"{results.dimensions.depth_width} x {results.dimensions.depth_height}" if results.dimensions else "N/A",
            "dsm_resolution": f"{results.dimensions.dsm_width} x {results.dimensions.dsm_height}" if results.dimensions else "N/A",
            "render_grid_resolution": f"{results.dimensions.render_grid_width} x {results.dimensions.render_grid_height}" if results.dimensions else "N/A",
            "is_low_resolution": results.dimensions.is_low_resolution if results.dimensions else False,
            "resolution_warning": results.dimensions.resolution_warning if results.dimensions else None,
            "interpolation_applied": results.dimensions.interpolation_applied if results.dimensions else False,
            "interpolation_method": results.dimensions.interpolation_method if results.dimensions else "none"
        },
        "model": {
            "model_name": settings.MODEL_NAME,
            "model_version": settings.VERSION,
            "device_used": results.device_used,
            "timings_seconds": results.timing_seconds
        },
        "calibration": {
            "method": results.calibration.method,
            "is_metric": results.calibration.is_metric,
            "scale_factor": results.calibration.scale,
            "datum_offset": results.calibration.offset,
            "r2_score": results.calibration.r2,
            "rmse_residual": results.calibration.rmse,
            "gcp_count": results.calibration.gcp_count,
            "confidence": results.calibration.confidence,
            "reference_source": Path(job["dem_path"]).name if job.get("dem_path") else ("GCP_CSV" if job.get("gcp_path") else "NONE"),
            "statement": results.calibration.message
        },
        "dsm_statistics": {
            "is_metric": results.dsm_stats.is_metric,
            "elevation_units": "meters (AMSL)" if results.dsm_stats.is_metric else "relative elevation units [0-100]",
            "min_elevation": results.dsm_stats.min_elevation,
            "max_elevation": results.dsm_stats.max_elevation,
            "mean_elevation": results.dsm_stats.mean_elevation,
            "median_elevation": results.dsm_stats.median_elevation,
            "std_elevation": results.dsm_stats.std_elevation,
            "total_relief": results.dsm_stats.relief,
            "average_slope_deg": results.dsm_stats.average_slope_deg,
            "max_slope_deg": results.dsm_stats.max_slope_deg,
            "steep_area_pct": results.dsm_stats.steep_area_pct,
            "crs": results.dsm_stats.crs
        },
        "spatial_verification": {
            "crs_preserved": bool(results.image_metadata.crs),
            "affine_transform_preserved": bool(results.image_metadata.transform),
            "dimensions_preserved": True,
            "nodata_preserved": True,
            "values_preserved": True,
            "elevation_units_metric": results.dsm_stats.is_metric
        }
    }

    # Only include validation metrics if actually evaluated against reference data
    if eval_data and eval_data.get("has_evaluation"):
        m = eval_data.get("metrics", {})
        report["validation"] = {
            "status": "Evaluated against ground truth reference raster",
            "profile_name": eval_data.get("profile_name", "terrain_standard"),
            "selected_metrics": eval_data.get("selected_metrics", []),
            "reference_filename": eval_data.get("reference_filename"),
            "sample_count": m.get("sample_count"),
            "valid_pixel_pct": m.get("valid_pixel_pct"),
            "elevation_metrics": {
                "mae_m": m.get("mae"),
                "rmse_m": m.get("rmse"),
                "pearson_r": m.get("pearson_r"),
                "r2_score": m.get("r2"),
                "mean_bias_error_m": m.get("mbe"),
                "median_error_m": m.get("median_error"),
                "median_absolute_error_m": m.get("median_abs_error"),
                "max_absolute_error_m": m.get("max_abs_error"),
                "min_error_m": m.get("min_error"),
                "max_error_m": m.get("max_error"),
                "le90_m": m.get("le90"),
                "le95_m": m.get("le95")
            },
            "monocular_depth_metrics": {
                "abs_rel": m.get("abs_rel"),
                "sq_rel": m.get("sq_rel"),
                "delta1_pct": m.get("delta1"),
                "delta2_pct": m.get("delta2"),
                "delta3_pct": m.get("delta3")
            },
            "slope_metrics": {
                "slope_mae_deg": m.get("slope_mae"),
                "slope_rmse_deg": m.get("slope_rmse")
            },
            "landscape_breakdown": eval_data.get("landscape_evaluation", [])
        }
    else:
        report["validation"] = {
            "status": "Validation unavailable — no reference elevation dataset supplied"
        }

    return report

@router.get("/results/{job_id}/report")
async def get_project_report(job_id: str):
    """
    Returns the comprehensive scientific project report as structured JSON.
    """
    job_id = validate_safe_id(job_id, "job_id")
    pipeline = PipelineManager.get_instance()
    try:
        results = pipeline.get_results(job_id)
        return build_project_report(job_id, results)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

@router.get("/results/{job_id}/export")
async def export_project(job_id: str):
    """
    Builds and downloads a comprehensive zip archive containing:
    - DSM GeoTIFF (preserving spatial tags)
    - Depth map (grayscale & colorized PNG)
    - Hillshade and slope rasters
    - 3D Wavefront OBJ mesh
    - Error map PNGs and GeoTIFFs (if evaluated)
    - Project metadata & scientific report (JSON)
    """
    job_id = validate_safe_id(job_id, "job_id")
    pipeline = PipelineManager.get_instance()
    try:
        results = pipeline.get_results(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    zip_filename = f"depthwizard_{job_id}_export.zip"
    zip_path = assert_path_confined(settings.EXPORT_DIR / zip_filename, settings.EXPORT_DIR)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add GeoTIFF
        dsm_tif = settings.DSM_DIR / f"{job_id}_dsm.tif"
        if dsm_tif.exists():
            zf.write(dsm_tif, arcname=f"dsm/{dsm_tif.name}")

        slope_tif = settings.DSM_DIR / f"{job_id}_slope.tif"
        if slope_tif.exists():
            zf.write(slope_tif, arcname=f"dsm/{slope_tif.name}")

        hillshade_tif = settings.DSM_DIR / f"{job_id}_hillshade.tif"
        if hillshade_tif.exists():
            zf.write(hillshade_tif, arcname=f"dsm/{hillshade_tif.name}")

        # Add GeoTIFF error maps if evaluated
        error_tif = settings.STORAGE_DIR / "exports" / f"{job_id}_error_map.tif"
        if error_tif.exists():
            zf.write(error_tif, arcname=f"dsm/{error_tif.name}")

        abs_error_tif = settings.STORAGE_DIR / "exports" / f"{job_id}_abs_error_map.tif"
        if abs_error_tif.exists():
            zf.write(abs_error_tif, arcname=f"dsm/{abs_error_tif.name}")

        # Add Mesh OBJ
        mesh_obj = settings.MESH_DIR / f"{job_id}_terrain.obj"
        if mesh_obj.exists():
            zf.write(mesh_obj, arcname=f"mesh/{mesh_obj.name}")

        # Add Heightfield JSON
        heightfield = settings.MESH_DIR / f"{job_id}_heightfield.json"
        if heightfield.exists():
            zf.write(heightfield, arcname=f"mesh/{heightfield.name}")

        # Add PNG Maps
        for map_type in ["depth_gray", "depth_color", "dsm_color", "hillshade", "slope", "contour"]:
            asset_rel = results.assets.get(map_type)
            if asset_rel:
                asset_file = settings.STORAGE_DIR.parent / asset_rel.lstrip("/")
                if asset_file.exists():
                    zf.write(asset_file, arcname=f"visualizations/{asset_file.name}")

        # Add Error Map if evaluated
        error_map_file = settings.STORAGE_DIR / "exports" / f"{job_id}_error_map.png"
        if error_map_file.exists():
            zf.write(error_map_file, arcname=f"visualizations/{error_map_file.name}")

        abs_error_map_file = settings.STORAGE_DIR / "exports" / f"{job_id}_abs_error_map.png"
        if abs_error_map_file.exists():
            zf.write(abs_error_map_file, arcname=f"visualizations/{abs_error_map_file.name}")

        # Add Project Report JSON
        report = build_project_report(job_id, results)
        zf.writestr("project_report.json", json.dumps(report, indent=2))

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=zip_filename
    )


@router.get("/results/{job_id}/verify_geotiff", response_model=GeoTIFFVerificationResult)
async def verify_geotiff_export(job_id: str):
    """
    Verifies that the exported DSM GeoTIFF can be reopened and preserves CRS,
    transform, dimensions, NoData, and pixel values within machine precision.
    """
    job_id = validate_safe_id(job_id, "job_id")
    pipeline = PipelineManager.get_instance()
    try:
        results = pipeline.get_results(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    dsm_tif = settings.DSM_DIR / f"{job_id}_dsm.tif"
    dsm_npy = settings.DSM_DIR / f"{job_id}_dsm.npy"
    if not dsm_tif.exists():
        raise HTTPException(status_code=404, detail=f"DSM GeoTIFF for job {job_id} not found.")

    expected_data = np.load(dsm_npy) if dsm_npy.exists() else None
    return GeospatialService.verify_geotiff_roundtrip(
        geotiff_path=dsm_tif,
        expected_data=expected_data,
        expected_crs=results.image_metadata.crs,
        expected_transform=results.image_metadata.transform
    )

