import uuid
import shutil
from pathlib import Path
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException

from app.config import settings
from app.services.geospatial_service import GeospatialService
from app.services.depth_service import PipelineManager
from app.schemas.schemas import UploadResponse

router = APIRouter(prefix="", tags=["Samples"])

SAMPLE_CATALOG = [
    {
        "id": "himalayan_valley",
        "title": "Himalayan Ridge & Valley (ISRO Disaster Demo)",
        "description": "Georeferenced satellite scene with significant elevation relief (UTM Zone 43N). Includes true reference DEM and 6 GCPs for metric calibration and validation.",
        "type": "georeferenced",
        "format": "GeoTIFF",
        "has_dem": True,
        "has_gcps": True,
        "image_file": "himalayan_scene.tif",
        "dem_file": "himalayan_ref_dem.tif",
        "gcp_file": "himalayan_gcps.csv"
    },
    {
        "id": "coastal_estuary",
        "title": "Coastal Estuary & Delta (Flood Hazard Demo)",
        "description": "Low-lying coastal terrain with river channels and urban structures. Ideal for flood simulation and elevation risk visualization.",
        "type": "georeferenced",
        "format": "GeoTIFF",
        "has_dem": True,
        "has_gcps": False,
        "image_file": "coastal_scene.tif",
        "dem_file": "coastal_ref_dem.tif",
        "gcp_file": None
    },
    {
        "id": "aerial_urban_flood",
        "title": "Post-Disaster Aerial Survey (Non-Georeferenced)",
        "description": "High-resolution RGB drone survey of urban infrastructure and flooded roadways. Generates Relative Digital Surface Model (rDSM).",
        "type": "non_georeferenced",
        "format": "JPEG",
        "has_dem": False,
        "has_gcps": False,
        "image_file": "aerial_survey.jpg",
        "dem_file": None,
        "gcp_file": None
    }
]

@router.get("/samples", response_model=List[Dict[str, Any]])
async def list_sample_datasets():
    """
    Returns pre-bundled sample remote sensing datasets for 1-click live testing.
    """
    return SAMPLE_CATALOG

@router.post("/samples/{sample_id}/load", response_model=UploadResponse)
async def load_sample_dataset(sample_id: str):
    """
    Instantly initializes a reconstruction job using pre-packaged remote-sensing sample data.
    """
    selected = next((s for s in SAMPLE_CATALOG if s["id"] == sample_id), None)
    if not selected:
        raise HTTPException(status_code=404, detail=f"Sample dataset '{sample_id}' not found.")

    sample_src_dir = settings.SAMPLES_DIR / sample_id
    if not sample_src_dir.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Sample directory '{sample_src_dir}' not found on server."
        )

    job_id = f"dw_demo_{uuid.uuid4().hex[:8]}"
    job_dir = settings.UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    img_name = selected["image_file"]
    src_img = sample_src_dir / img_name
    dest_img = job_dir / img_name
    shutil.copyfile(src_img, dest_img)

    dest_dem = None
    if selected.get("dem_file"):
        src_dem = sample_src_dir / selected["dem_file"]
        if src_dem.exists():
            dest_dem = job_dir / selected["dem_file"]
            shutil.copyfile(src_dem, dest_dem)

    dest_gcp = None
    if selected.get("gcp_file"):
        src_gcp = sample_src_dir / selected["gcp_file"]
        if src_gcp.exists():
            dest_gcp = job_dir / selected["gcp_file"]
            shutil.copyfile(src_gcp, dest_gcp)

    metadata, _ = GeospatialService.inspect_file(dest_img)

    pipeline = PipelineManager.get_instance()
    pipeline.register_job(
        job_id=job_id,
        image_path=dest_img,
        metadata=metadata,
        dem_path=dest_dem,
        gcp_path=dest_gcp
    )

    return UploadResponse(
        job_id=job_id,
        filename=img_name,
        metadata=metadata,
        has_dem=dest_dem is not None,
        has_gcp=dest_gcp is not None,
        message=f"Demo dataset '{selected['title']}' loaded successfully."
    )
