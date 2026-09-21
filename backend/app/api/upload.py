import uuid
import shutil
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.config import settings
from app.services.geospatial_service import GeospatialService
from app.services.depth_service import PipelineManager
from app.schemas.schemas import UploadResponse, DEMMetadata, GCPItem
from app.utils.security import save_upload_file_safely, sanitize_filename

router = APIRouter(prefix="", tags=["Upload"])

@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    image: UploadFile = File(...),
    dem: Optional[UploadFile] = File(None),
    gcp: Optional[UploadFile] = File(None)
):
    """
    Accepts remote-sensing imagery (PNG, JPG, TIFF, GeoTIFF) along with optional
    reference DEM (SRTM/CartoDEM GeoTIFF) and optional Ground Control Points (CSV).
    Extracts spatial metadata, verifies spatial references, parses GCPs, and registers a new reconstruction job.
    """
    clean_filename = sanitize_filename(image.filename)
    ext = Path(clean_filename).suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image format '{ext}'. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )

    job_id = f"dw_{uuid.uuid4().hex[:10]}"
    job_dir = settings.UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save main image safely with size limits
    image_save_path = job_dir / f"input{ext}"
    await save_upload_file_safely(image, image_save_path)

    try:
        # Inspect imagery and extract geospatial metadata
        metadata, _ = GeospatialService.inspect_file(image_save_path)
    except Exception as e:
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse image file: {str(e)}")

    # Save and inspect optional DEM
    dem_save_path = None
    dem_metadata: Optional[DEMMetadata] = None
    if dem and dem.filename:
        clean_dem_name = sanitize_filename(dem.filename)
        dem_ext = Path(clean_dem_name).suffix.lower()
        if dem_ext in [".tif", ".tiff"]:
            dem_save_path = job_dir / f"dem{dem_ext}"
            await save_upload_file_safely(dem, dem_save_path)
            dem_metadata = GeospatialService.inspect_dem_file(
                dem_path=dem_save_path,
                image_crs=metadata.crs,
                image_bounds=metadata.bounds
            )

    # Save and parse optional GCPs
    gcp_save_path = None
    parsed_gcps: Optional[List[GCPItem]] = None
    if gcp and gcp.filename:
        clean_gcp_name = sanitize_filename(gcp.filename)
        gcp_ext = Path(clean_gcp_name).suffix.lower()
        if gcp_ext in [".csv", ".txt"]:
            gcp_save_path = job_dir / f"gcps{gcp_ext}"
            await save_upload_file_safely(gcp, gcp_save_path)
            
            pipeline = PipelineManager.get_instance()
            try:
                parsed_gcps = pipeline._parse_gcp_csv(gcp_save_path)
            except Exception as e:
                parsed_gcps = []

    # Register job
    pipeline = PipelineManager.get_instance()
    pipeline.register_job(
        job_id=job_id,
        image_path=image_save_path,
        metadata=metadata,
        dem_path=dem_save_path,
        gcp_path=gcp_save_path,
        dem_metadata=dem_metadata
    )

    msg = "Georeferenced GeoTIFF identified." if metadata.is_georeferenced else "Standard non-georeferenced imagery identified (will generate rDSM)."

    return UploadResponse(
        job_id=job_id,
        filename=image.filename,
        metadata=metadata,
        has_dem=dem_save_path is not None,
        dem_metadata=dem_metadata,
        has_gcp=gcp_save_path is not None,
        parsed_gcps=parsed_gcps,
        message=msg
    )
