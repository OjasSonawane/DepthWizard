import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.services.depth_service import PipelineManager
from app.services.dataset_service import DatasetService
from app.services.geospatial_service import GeospatialService
from app.schemas.schemas import (
    JobStatus, ReconstructionSummary, GCPCalibrationRequest,
    TerrainProfileRequest, TerrainProfileResponse,
    FloodSimulationRequest, FloodSimulationResponse,
    ProcessDatasetRequest, CreateJobRequest, CentralJobModel
)
from pathlib import Path
from app.utils.security import validate_safe_id

router = APIRouter(prefix="", tags=["Processing"])
executor = ThreadPoolExecutor(max_workers=2)

@router.post("/jobs/create", response_model=JobStatus)
async def create_job(req: CreateJobRequest):
    """
    Creates and enqueues a new central processing reconstruction job with initial status QUEUED.
    """
    pipeline = PipelineManager.get_instance()
    ds_service = DatasetService.get_instance()

    if req.dataset_id:
        ds_id = validate_safe_id(req.dataset_id, "dataset_id")
        try:
            ds = ds_service.get_dataset(ds_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Dataset '{req.dataset_id}' not found.")

        files = ds_service.get_dataset_files(req.dataset_id)
        img_path = files["image_path"]
        if not img_path or not img_path.exists():
            raise HTTPException(status_code=404, detail=f"Image for dataset '{req.dataset_id}' not found.")

        dem_path = files.get("dem_path")
        gcp_path = files.get("gcp_path")

        meta, _ = GeospatialService.inspect_file(img_path)
        dem_metadata = None
        if dem_path and dem_path.exists():
            dem_metadata = GeospatialService.inspect_dem_file(
                dem_path=dem_path,
                image_crs=meta.crs,
                image_bounds=meta.bounds
            )

        job_id = f"dw_job_{uuid.uuid4().hex[:8]}"
        job_status = pipeline.register_job(
            job_id=job_id,
            image_path=img_path,
            metadata=meta,
            dem_path=dem_path,
            gcp_path=gcp_path,
            dem_metadata=dem_metadata,
            dataset_id=req.dataset_id
        )
        return job_status

    elif req.image_path:
        img_p = Path(req.image_path)
        if not img_p.exists():
            raise HTTPException(status_code=404, detail=f"Image path '{req.image_path}' not found.")

        meta, _ = GeospatialService.inspect_file(img_p)
        dem_p = Path(req.dem_path) if req.dem_path and Path(req.dem_path).exists() else None
        gcp_p = Path(req.gcp_path) if req.gcp_path and Path(req.gcp_path).exists() else None

        dem_metadata = None
        if dem_p:
            dem_metadata = GeospatialService.inspect_dem_file(
                dem_path=dem_p,
                image_crs=meta.crs,
                image_bounds=meta.bounds
            )

        job_id = f"dw_job_{uuid.uuid4().hex[:8]}"
        return pipeline.register_job(
            job_id=job_id,
            image_path=img_p,
            metadata=meta,
            dem_path=dem_p,
            gcp_path=gcp_p,
            dem_metadata=dem_metadata
        )
    else:
        raise HTTPException(status_code=400, detail="Must provide either dataset_id or image_path.")

@router.post("/jobs/{job_id}/start", response_model=ReconstructionSummary)
async def start_job(job_id: str):
    """
    Starts pipeline processing for a queued job.
    """
    job_id = validate_safe_id(job_id, "job_id")
    return await process_job(job_id)

@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """
    Returns real-time processing status, active stage, and progress bar values.
    """
    job_id = validate_safe_id(job_id, "job_id")
    pipeline = PipelineManager.get_instance()
    try:
        return pipeline.get_job_status(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

@router.post("/process/{job_id}", response_model=ReconstructionSummary)
async def process_job(job_id: str):
    """
    Executes the full 12-stage single-view 3D reconstruction pipeline.
    """
    job_id = validate_safe_id(job_id, "job_id")
    pipeline = PipelineManager.get_instance()
    if job_id not in pipeline.jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    job = pipeline.jobs[job_id]
    active_statuses = {"VALIDATING", "INFERENCE", "CALIBRATING", "GENERATING_DSM", "VALIDATING_RESULT"}
    if job.get("status") in active_statuses:
        raise HTTPException(
            status_code=409,
            detail=f"Job '{job_id}' is already actively processing (status: {job['status']})."
        )

    if job.get("dataset_id"):
        ds_svc = DatasetService.get_instance()
        if job["dataset_id"] in ds_svc.datasets:
            ds = ds_svc.datasets[job["dataset_id"]]
            if ds.input_validation and ds.input_validation.status == "rejected":
                raise HTTPException(
                    status_code=422,
                    detail=f"Reconstruction blocked: Input image was rejected by optical content validator ({ds.input_validation.rejection_reason}). Please select satellite, aerial, drone, or terrain imagery."
                )

    try:
        loop = asyncio.get_event_loop()
        summary = await loop.run_in_executor(executor, pipeline.run_pipeline, job_id)
        return summary
    except RuntimeError as re:
        raise HTTPException(status_code=409, detail=str(re))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reconstruction failed: {str(e)}")

@router.post("/reconstruction/process", response_model=ReconstructionSummary)
async def process_dataset(req: ProcessDatasetRequest):
    """
    Executes 3D elevation reconstruction for the specified dataset.
    """
    ds_id = validate_safe_id(req.dataset_id, "dataset_id")
    ds_service = DatasetService.get_instance()
    try:
        ds = ds_service.get_dataset(ds_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dataset '{ds_id}' not found.")

    if ds.input_validation and ds.input_validation.status == "rejected":
        raise HTTPException(
            status_code=422,
            detail=f"Reconstruction blocked: Input image was rejected by optical content validator ({ds.input_validation.rejection_reason}). Please select satellite, aerial, drone, or terrain imagery."
        )

    files = ds_service.get_dataset_files(ds_id)
    img_path = files["image_path"]
    if not img_path or not img_path.exists():
        raise HTTPException(status_code=404, detail=f"Image file for dataset '{ds_id}' not found.")

    dem_path = files.get("dem_path")
    gcp_path = files.get("gcp_path")

    meta, _ = GeospatialService.inspect_file(img_path)
    dem_metadata = None
    if dem_path and dem_path.exists():
        dem_metadata = GeospatialService.inspect_dem_file(
            dem_path=dem_path,
            image_crs=meta.crs,
            image_bounds=meta.bounds
        )

    pipeline = PipelineManager.get_instance()
    job_id = f"dw_job_{uuid.uuid4().hex[:8]}"
    pipeline.register_job(
        job_id=job_id,
        image_path=img_path,
        metadata=meta,
        dem_path=dem_path,
        gcp_path=gcp_path,
        dem_metadata=dem_metadata,
        dataset_id=ds_id
    )

    try:
        loop = asyncio.get_event_loop()
        summary = await loop.run_in_executor(executor, pipeline.run_pipeline, job_id)
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reconstruction failed: {str(e)}")

@router.post("/gcp/{job_id}", response_model=ReconstructionSummary)
async def calibrate_with_gcps(job_id: str, req: GCPCalibrationRequest):
    """
    Calibrates or recalibrates the elevation surface using provided Ground Control Points (GCPs).
    """
    job_id = validate_safe_id(job_id, "job_id")
    pipeline = PipelineManager.get_instance()
    try:
        # Save GCPs to job and re-run calibration
        job = pipeline.jobs[job_id]
        from pathlib import Path
        gcp_path = Path(job["image_path"]).parent / "gcps_input.csv"
        with open(gcp_path, "w") as f:
            f.write("id,x,y,elevation\n")
            for gcp in req.gcps:
                f.write(f"{gcp.id},{gcp.x},{gcp.y},{gcp.elevation}\n")
        job["gcp_path"] = str(gcp_path)
        
        loop = asyncio.get_event_loop()
        summary = await loop.run_in_executor(executor, pipeline.run_pipeline, job_id)
        return summary
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GCP Calibration failed: {str(e)}")

@router.post("/analysis/profile/{job_id}", response_model=TerrainProfileResponse)
async def get_terrain_profile(job_id: str, req: TerrainProfileRequest):
    """
    Extracts cross-sectional elevation profile along user-drawn transect.
    """
    job_id = validate_safe_id(job_id, "job_id")
    pipeline = PipelineManager.get_instance()
    try:
        return pipeline.compute_terrain_profile(
            job_id=job_id,
            x1_pct=req.x1_pct,
            y1_pct=req.y1_pct,
            x2_pct=req.x2_pct,
            y2_pct=req.y2_pct,
            samples=req.samples
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Profile extraction failed: {str(e)}")

@router.post("/analysis/flood/{job_id}", response_model=FloodSimulationResponse)
async def simulate_flood_risk(job_id: str, req: FloodSimulationRequest):
    """
    Performs illustrative elevation-based inundation analysis below selected water elevation threshold.
    """
    job_id = validate_safe_id(job_id, "job_id")
    pipeline = PipelineManager.get_instance()
    try:
        return pipeline.simulate_flood(
            job_id=job_id,
            water_elevation=req.water_elevation
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Flood simulation failed: {str(e)}")
