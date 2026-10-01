import os
from pathlib import Path
from pydantic_settings import BaseSettings

# Configure writable cache directories
storage_cache = Path(__file__).resolve().parent.parent / "storage"
os.environ["MPLCONFIGDIR"] = str(storage_cache)
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import torch

class Settings(BaseSettings):
    PROJECT_NAME: str = "DepthWizard"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    
    # Base directories
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    STORAGE_DIR: Path = BASE_DIR / "storage"
    DATASETS_DIR: Path = STORAGE_DIR / "datasets"
    UPLOAD_DIR: Path = STORAGE_DIR / "uploads"
    DEPTH_DIR: Path = STORAGE_DIR / "depth"
    DSM_DIR: Path = STORAGE_DIR / "dsm"
    MESH_DIR: Path = STORAGE_DIR / "meshes"
    EXPORT_DIR: Path = STORAGE_DIR / "exports"
    DATA_DIR: Path = BASE_DIR.parent / "data"
    SAMPLES_DIR: Path = DATA_DIR / "samples"
    
    # Limits
    MAX_UPLOAD_SIZE_MB: int = 100
    ALLOWED_EXTENSIONS: list[str] = [".png", ".jpg", ".jpeg", ".tif", ".tiff"]
    
    # ML settings
    MODEL_NAME: str = "depth-anything/Depth-Anything-V2-Small-hf"
    ALT_MODEL_NAME: str = "Intel/dpt-hybrid-midas"
    
    @property
    def DEVICE(self) -> str:
        if torch.cuda.is_available():
            return "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

settings = Settings()

# Ensure directories exist
for directory in [
    settings.STORAGE_DIR,
    settings.DATASETS_DIR,
    settings.UPLOAD_DIR,
    settings.DEPTH_DIR,
    settings.DSM_DIR,
    settings.MESH_DIR,
    settings.EXPORT_DIR,
    settings.DATA_DIR,
    settings.SAMPLES_DIR
]:
    directory.mkdir(parents=True, exist_ok=True)
