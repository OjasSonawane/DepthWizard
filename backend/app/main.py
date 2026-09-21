import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models.depth_model import DepthEstimator
from app.services.dataset_service import DatasetService
from app.api import upload, processing, visualization, evaluation, samples, export, datasets, benchmarks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("depthwizard")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing DepthWizard backend...")
    logger.info(f"Target compute device: {settings.DEVICE.upper()}")
    # Initialize persistent datasets registry
    try:
        ds_service = DatasetService.get_instance()
        logger.info(f"DatasetService ready: {len(ds_service.datasets)} datasets indexed.")
    except Exception as e:
        logger.error(f"Failed to initialize DatasetService: {e}", exc_info=True)

    # Preload model in background or on start
    try:
        estimator = DepthEstimator.get_instance()
        logger.info(f"DepthEstimator ready (Fallback mode: {estimator.is_fallback})")
    except Exception as e:
        logger.warning(f"Deferred model loading: {e}")
    yield
    logger.info("Shutting down DepthWizard backend.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Single-view AI remote-sensing 3D terrain reconstruction platform for ISRO Disaster Management.",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static file directories for generated visualizations & assets
app.mount("/storage", StaticFiles(directory=str(settings.STORAGE_DIR)), name="storage")

# Health check
@app.get("/api/health")
async def health_check():
    estimator = DepthEstimator.get_instance()
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "device": settings.DEVICE.upper(),
        "model_loaded": estimator.is_loaded,
        "is_fallback_mode": estimator.is_fallback,
        "storage_dir": str(settings.STORAGE_DIR)
    }

# Include routers
app.include_router(upload.router, prefix=settings.API_PREFIX)
app.include_router(datasets.router, prefix=settings.API_PREFIX)
app.include_router(processing.router, prefix=settings.API_PREFIX)
app.include_router(visualization.router, prefix=settings.API_PREFIX)
app.include_router(evaluation.router, prefix=settings.API_PREFIX)
app.include_router(samples.router, prefix=settings.API_PREFIX)
app.include_router(export.router, prefix=settings.API_PREFIX)
app.include_router(benchmarks.router, prefix=settings.API_PREFIX)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
