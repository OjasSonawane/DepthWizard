import tempfile
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.services.dataset_service import DatasetService
from app.services.image_validator import ImageValidator
from app.schemas.schemas import DatasetSummary, DatasetListResponse, InputValidationResult
from app.utils.security import validate_safe_id, sanitize_filename, save_upload_file_safely
from app.config import settings

router = APIRouter(prefix="/datasets", tags=["Datasets"])

@router.post("/validate", response_model=InputValidationResult)
async def validate_dataset_image(
    image: UploadFile = File(...)
):
    """
    Validates uploaded image raster for optical remote-sensing suitability
    before persistent storage or processing.
    """
    clean_name = sanitize_filename(image.filename)
    ext = Path(clean_name).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        await save_upload_file_safely(image, tmp_path)
        val_result = ImageValidator.validate_image(tmp_path, filename=clean_name)
        return val_result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Image validation inspection failed: {str(e)}")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

@router.get("", response_model=DatasetListResponse)
async def list_datasets():
    """
    Returns unified list of both user-uploaded datasets and preloaded demonstration datasets.
    """
    ds_service = DatasetService.get_instance()
    all_datasets = ds_service.get_all_datasets()
    return DatasetListResponse(
        datasets=all_datasets,
        active_dataset_id=ds_service.active_dataset_id
    )

@router.post("/upload", response_model=DatasetSummary)
async def upload_dataset(
    image: UploadFile = File(...),
    dem: Optional[UploadFile] = File(None),
    gcp: Optional[UploadFile] = File(None)
):
    """
    Uploads optical imagery (GeoTIFF, PNG, JPG) with optional reference DEM and GCPs.
    Persistently stores the dataset, extracts metadata, generates thumbnails, and returns summary.
    """
    ds_service = DatasetService.get_instance()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    img_bytes = await image.read()
    if len(img_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded image is empty (0 bytes).")
    if len(img_bytes) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Uploaded image exceeds maximum allowed limit of {settings.MAX_UPLOAD_SIZE_MB}MB.")

    dem_bytes = await dem.read() if dem else None
    if dem_bytes and len(dem_bytes) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Uploaded DEM exceeds maximum allowed limit of {settings.MAX_UPLOAD_SIZE_MB}MB.")
    dem_name = sanitize_filename(dem.filename) if dem else None

    gcp_bytes = await gcp.read() if gcp else None
    if gcp_bytes and len(gcp_bytes) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Uploaded GCP file exceeds maximum allowed limit of {settings.MAX_UPLOAD_SIZE_MB}MB.")
    gcp_name = sanitize_filename(gcp.filename) if gcp else None
    clean_img_name = sanitize_filename(image.filename)

    try:
        summary = ds_service.create_user_dataset(
            image_bytes=img_bytes,
            original_filename=clean_img_name,
            dem_bytes=dem_bytes,
            dem_filename=dem_name,
            gcp_bytes=gcp_bytes,
            gcp_filename=gcp_name
        )
        return summary
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create dataset: {str(e)}")

@router.get("/{dataset_id}", response_model=DatasetSummary)
async def get_dataset(dataset_id: str):
    """
    Returns metadata and status for a specific dataset.
    """
    dataset_id = validate_safe_id(dataset_id, "dataset_id")
    ds_service = DatasetService.get_instance()
    try:
        return ds_service.get_dataset(dataset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found.")

@router.get("/{dataset_id}/thumbnail")
async def get_dataset_thumbnail(dataset_id: str):
    """
    Returns the real 256x256 image thumbnail for the dataset.
    """
    dataset_id = validate_safe_id(dataset_id, "dataset_id")
    ds_service = DatasetService.get_instance()
    try:
        thumb_path = ds_service.get_thumbnail_path(dataset_id)
        return FileResponse(thumb_path, media_type="image/jpeg")
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found.")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Thumbnail image not found.")

@router.get("/{dataset_id}/preview")
async def get_dataset_preview(dataset_id: str):
    """
    Returns the real browser-friendly preview image for the dataset.
    """
    dataset_id = validate_safe_id(dataset_id, "dataset_id")
    ds_service = DatasetService.get_instance()
    try:
        prev_path = ds_service.get_preview_path(dataset_id)
        return FileResponse(prev_path, media_type="image/jpeg")
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found.")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Preview image not found.")

@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str):
    """
    Deletes a user-uploaded dataset and its persistent files.
    """
    dataset_id = validate_safe_id(dataset_id, "dataset_id")
    ds_service = DatasetService.get_instance()
    try:
        ds_service.delete_dataset(dataset_id)
        return {
            "success": True,
            "message": f"Dataset '{dataset_id}' deleted successfully.",
            "active_dataset_id": ds_service.active_dataset_id
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found.")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete dataset: {str(e)}")

@router.post("/{dataset_id}/select", response_model=DatasetSummary)
async def select_dataset(dataset_id: str):
    """
    Marks the dataset as the active dataset in the backend session.
    """
    dataset_id = validate_safe_id(dataset_id, "dataset_id")
    ds_service = DatasetService.get_instance()
    try:
        return ds_service.select_dataset(dataset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found.")

@router.post("/{dataset_id}/prepare-job")
async def prepare_dataset_job(dataset_id: str):
    """
    Registers a job for the dataset and returns the job_id for real-time tracking and execution.
    """
    dataset_id = validate_safe_id(dataset_id, "dataset_id")
    ds_service = DatasetService.get_instance()
    try:
        job_id = ds_service.prepare_job(dataset_id)
        return {"job_id": job_id, "dataset_id": dataset_id}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to prepare job: {str(e)}")
