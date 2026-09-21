import json
import shutil
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.config import settings
from app.services.depth_service import PipelineManager
from app.schemas.schemas import EvaluationResponse, EvaluationConfigRequest

router = APIRouter(prefix="", tags=["Evaluation"])

@router.post("/evaluate/{job_id}", response_model=EvaluationResponse)
async def evaluate_dsm(
    job_id: str,
    reference_file: UploadFile = File(...),
    profile: Optional[str] = Form("terrain_standard"),
    selected_metrics: Optional[str] = Form(None)
):
    """
    Accepts reference elevation raster (GeoTIFF / DEM / DSM).
    Co-registers with predicted DSM and computes scientific validation metrics:
    MAE, RMSE, Pearson Correlation, MBE, R2, LE90, LE95, Monocular Depth, and Slope metrics.
    """
    pipeline = PipelineManager.get_instance()
    if job_id not in pipeline.jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    ext = Path(reference_file.filename).suffix.lower()
    if ext not in [".tif", ".tiff", ".png", ".jpg", ".npy"]:
        raise HTTPException(status_code=400, detail="Reference file must be a GeoTIFF, image, or NPY raster.")

    ref_save_dir = settings.STORAGE_DIR / "uploads" / job_id
    ref_save_dir.mkdir(parents=True, exist_ok=True)
    ref_path = ref_save_dir / f"reference{ext}"

    with open(ref_path, "wb") as f:
        shutil.copyfileobj(reference_file.file, f)

    # Parse selected_metrics if supplied as JSON or comma separated string
    parsed_metrics: Optional[List[str]] = None
    if selected_metrics:
        try:
            parsed_metrics = json.loads(selected_metrics)
            if not isinstance(parsed_metrics, list):
                parsed_metrics = [str(selected_metrics)]
        except Exception:
            parsed_metrics = [m.strip() for m in selected_metrics.split(",") if m.strip()]

    try:
        eval_resp = pipeline.evaluate(
            job_id=job_id,
            ref_file_path=ref_path,
            profile=profile,
            selected_metrics=parsed_metrics
        )
        return eval_resp
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")

@router.post("/evaluate/{job_id}/configure", response_model=EvaluationResponse)
async def configure_evaluation_metrics(
    job_id: str,
    req: EvaluationConfigRequest
):
    """
    Reconfigures validation metric calculations and profile without requiring DEM re-upload.
    """
    pipeline = PipelineManager.get_instance()
    if job_id not in pipeline.jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    try:
        return pipeline.configure_evaluation(
            job_id=job_id,
            profile=req.profile or "terrain_standard",
            selected_metrics=req.selected_metrics
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Configuration failed: {str(e)}")

@router.get("/evaluate/{job_id}", response_model=EvaluationResponse)
async def get_evaluation_status(job_id: str):
    """
    Returns existing validation metrics or prompt to upload reference elevation data.
    """
    pipeline = PipelineManager.get_instance()
    try:
        return pipeline.get_evaluation(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
