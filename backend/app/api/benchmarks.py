import logging
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.schemas.gamus_schemas import (
    GAMUSCatalogItem,
    GAMUSEvaluationRequest,
    GAMUSEvaluationResult,
    GAMUSSampleRecord,
)
from app.services.gamus_service import (
    GAMUSService,
    SampleNotFoundError,
    SpatialMismatchError,
    TestSetCalibrationProhibitedError,
    SplitNotSupportedError,
)
from app.utils.security import validate_safe_id, assert_path_confined

logger = logging.getLogger("depthwizard.api.benchmarks")
router = APIRouter(prefix="/benchmarks/gamus", tags=["benchmarks"])
gamus_service = GAMUSService()


@router.get("/catalog", response_model=List[GAMUSCatalogItem])
async def get_gamus_catalog(split: Optional[str] = Query(None, description="Optional split filter: 'train', 'val', or 'test'")):
    """
    Query the GAMUS benchmark sample catalog without downloading the full dataset.
    Returns available sample IDs, split memberships, and cached status.
    """
    try:
        return gamus_service.list_catalog(split=split)
    except SplitNotSupportedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Catalog retrieval failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to query GAMUS catalog: {e}")


@router.get("/samples/{split}/{sample_id}", response_model=GAMUSSampleRecord)
async def get_gamus_sample_record(split: str, sample_id: str):
    """
    Stream or load a single GAMUS sample, verify exact RGB-to-height pairing,
    and return its certified benchmark sample record with explicit height semantics
    (AGL / nDSM in meters, non-absolute elevation).
    """
    split = validate_safe_id(split, "split")
    sample_id = validate_safe_id(sample_id, "sample_id")
    try:
        _, _, record = gamus_service.load_sample_arrays(split, sample_id)
        return record
    except SampleNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SpatialMismatchError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except SplitNotSupportedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error loading sample record for {sample_id} ({split}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load GAMUS sample: {e}")


@router.post("/evaluate", response_model=GAMUSEvaluationResult)
async def evaluate_gamus_sample(request: GAMUSEvaluationRequest):
    """
    Execute Depth Anything V2 inference on a GAMUS sample and compute scientific evaluation metrics.
    
    Strict Guardrails:
    - Calibrating directly on the test set is strictly prohibited (raises 400).
    - Height semantics are certified as Above Ground Level (AGL/nDSM) in meters.
    - Computes MAE, RMSE, Pearson r, Spearman rho, R2, MBE, LE90, LE95.
    - Generates signed error map, absolute error map, and publication-grade scatter plot.
    - Persists complete experiment metadata to disk.
    """
    try:
        result = gamus_service.evaluate_sample(request)
        return result
    except TestSetCalibrationProhibitedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SampleNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SpatialMismatchError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"GAMUS evaluation failed for {request.sample_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Benchmark evaluation failed: {e}")


@router.get("/experiments")
async def list_gamus_experiments():
    """List historical GAMUS benchmark experiment runs."""
    try:
        return gamus_service.list_experiments()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list experiments: {e}")


@router.get("/experiments/{experiment_id}")
async def get_gamus_experiment(experiment_id: str):
    """Retrieve full experiment record JSON for a specific benchmark run."""
    experiment_id = validate_safe_id(experiment_id, "experiment_id")
    exp = gamus_service.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found.")
    return exp


@router.get("/experiments/{experiment_id}/assets/{asset_name}")
async def get_gamus_experiment_asset(experiment_id: str, asset_name: str):
    """Serve visual diagnostic assets (error maps, scatter plot, predicted depth PNGs)."""
    experiment_id = validate_safe_id(experiment_id, "experiment_id")
    valid_assets = {
        "signed_error_map": "signed_error_map.png",
        "absolute_error_map": "absolute_error_map.png",
        "scatter_plot": "scatter_plot.png",
        "predicted_depth": "predicted_depth.png"
    }
    if asset_name not in valid_assets:
        raise HTTPException(status_code=400, detail=f"Invalid asset name. Must be one of {list(valid_assets.keys())}")

    raw_asset_path = gamus_service.experiments_dir / experiment_id / valid_assets[asset_name]
    asset_path = assert_path_confined(raw_asset_path, gamus_service.experiments_dir)
    if not asset_path.exists():
        raise HTTPException(status_code=404, detail="Asset file not found.")

    return FileResponse(path=str(asset_path), media_type="image/png")

