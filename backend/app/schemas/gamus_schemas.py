from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class GAMUSSplit(str, Enum):
    TRAIN = "train"
    VAL = "val"
    TEST = "test"


class CalibrationMode(str, Enum):
    ZERO_SHOT_RELATIVE = "zero_shot_relative"
    TRAIN_CALIBRATED_TRANSFER = "train_calibrated_transfer"
    DIRECT_FIT_TRAIN_VAL = "direct_fit_train_val"


class RGBMetadata(BaseModel):
    shape: List[int]
    dtype: str
    channels: int = 3
    min_val: int
    max_val: int
    channel_order: str = "RGB"


class ReferenceHeightMetadata(BaseModel):
    field_name: str = "AGL"
    type: str = "nDSM (Height Above Ground Level)"
    is_absolute_elevation: bool = False
    vertical_datum: str = "Ground Level (AGL = 0.0m)"
    units: str = "meters"
    shape: List[int]
    dtype: str = "float32"
    min_val: float
    max_val: float
    mean_val: float
    std_val: float
    valid_pixel_pct: float
    disclaimer: str = (
        "Reference height represents Above Ground Level (AGL / nDSM) in meters, "
        "NOT absolute elevation (AMSL)."
    )


class GAMUSSampleRecord(BaseModel):
    benchmark_name: str = "GAMUS"
    dataset_source: str = "earthflow/GAMUS (arXiv:2305.14914)"
    sample_id: str
    split: str
    rgb_metadata: RGBMetadata
    reference_metadata: ReferenceHeightMetadata
    created_at: str


class GAMUSCatalogItem(BaseModel):
    sample_id: str
    split: str
    img_file: str
    agl_file: str
    is_cached: bool


class GAMUSEvaluationRequest(BaseModel):
    split: str = Field(default="test", description="Dataset split: 'train', 'val', or 'test'")
    sample_id: str = Field(default="NYC_00735", description="Sample identifier (e.g. 'NYC_00735')")
    calibration_mode: CalibrationMode = Field(
        default=CalibrationMode.ZERO_SHOT_RELATIVE,
        description="Calibration strategy: 'zero_shot_relative', 'train_calibrated_transfer', or 'direct_fit_train_val'"
    )
    train_calibration_sample_id: Optional[str] = Field(
        default=None,
        description="Sample ID from train split used to derive scale/offset when calibration_mode is 'train_calibrated_transfer'"
    )
    scatter_sample_size: int = Field(
        default=2000,
        ge=100,
        le=20000,
        description="Number of subsampled points for scatter plot generation"
    )


class GAMUSScatterPoint(BaseModel):
    predicted: float
    reference: float


class GAMUSEvaluationMetrics(BaseModel):
    mae: float
    rmse: float
    pearson_r: float
    spearman_rho: float
    r2: float
    mbe: float
    median_abs_error: float
    max_abs_error: float
    le90: float
    le95: float
    valid_pixels: int


class CalibrationInfo(BaseModel):
    mode: str
    source_split: Optional[str] = None
    source_sample_id: Optional[str] = None
    scale: Optional[float] = None
    offset: Optional[float] = None
    applied_to_test: bool = False
    message: str


class GAMUSEvaluationResult(BaseModel):
    experiment_id: str
    benchmark_name: str = "GAMUS"
    dataset_source: str = "earthflow/GAMUS (arXiv:2305.14914)"
    sample_id: str
    split: str
    model_name: str
    device: str
    is_absolute_elevation: bool = False
    height_semantics: str = "nDSM (Height Above Ground Level / AGL)"
    height_units: str = "meters"
    calibration: CalibrationInfo
    metrics: GAMUSEvaluationMetrics
    scatter_points: List[GAMUSScatterPoint]
    assets: Dict[str, str]
    timings: Dict[str, float]


class GAMUSExperimentRecord(BaseModel):
    experiment_id: str
    timestamp: str
    sample_record: GAMUSSampleRecord
    evaluation_result: GAMUSEvaluationResult
    environment: Dict[str, Any]

