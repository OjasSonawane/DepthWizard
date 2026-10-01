from enum import Enum
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field

class ImageMetadata(BaseModel):
    width: int
    height: int
    format: str
    file_size_bytes: int
    is_georeferenced: bool
    crs: Optional[str] = None
    transform: Optional[List[float]] = None
    bounds: Optional[List[float]] = None  # [minx, miny, maxx, maxy]
    resolution: Optional[List[float]] = None  # [dx, dy]
    nodata: Optional[float] = None
    band_count: int = 3
    datatype: Optional[str] = "uint8"
    native_dtype: Optional[str] = "uint8"
    file_hash: Optional[str] = None
    classification: Optional[str] = "Non-georeferenced optical image"
    is_low_resolution: bool = False
    resolution_warning: Optional[str] = None

class DEMMetadata(BaseModel):
    filename: str
    crs: Optional[str] = None
    resolution: Optional[List[float]] = None
    bounds: Optional[List[float]] = None
    min_elevation: float
    max_elevation: float
    is_compatible: bool = True
    compatibility_note: Optional[str] = None

class GCPItem(BaseModel):
    id: Union[str, int]
    x: float  # Longitude or projected Easting / pixel X
    y: float  # Latitude or projected Northing / pixel Y
    elevation: float

class UploadResponse(BaseModel):
    job_id: str
    filename: str
    metadata: ImageMetadata
    has_dem: bool = False
    dem_metadata: Optional[DEMMetadata] = None
    has_gcp: bool = False
    parsed_gcps: Optional[List[GCPItem]] = None
    message: str

class JobState(str, Enum):
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    INFERENCE = "INFERENCE"
    CALIBRATING = "CALIBRATING"
    GENERATING_DSM = "GENERATING_DSM"
    VALIDATING_RESULT = "VALIDATING_RESULT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class ProcessingStage(BaseModel):
    stage_id: str
    name: str
    progress: int
    message: str
    is_current: bool = False
    is_done: bool = False

class CentralJobModel(BaseModel):
    job_id: str
    status: str
    input: Dict[str, Any]
    validation: Optional[Dict[str, Any]] = None
    depth: Optional[Dict[str, Any]] = None
    calibration: Optional[Dict[str, Any]] = None
    dsm: Optional[Dict[str, Any]] = None
    validation_result: Optional[Dict[str, Any]] = None
    artifacts: Dict[str, str] = Field(default_factory=dict)
    errors: Optional[str] = None

class JobStatus(BaseModel):
    job_id: str
    status: str  # QUEUED, VALIDATING, INFERENCE, CALIBRATING, GENERATING_DSM, VALIDATING_RESULT, COMPLETED, FAILED
    current_stage: str
    progress: int
    message: str
    stages: List[ProcessingStage] = []
    error: Optional[str] = None
    errors: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    validation: Optional[Dict[str, Any]] = None
    depth: Optional[Dict[str, Any]] = None
    calibration: Optional[Dict[str, Any]] = None
    dsm: Optional[Dict[str, Any]] = None
    validation_result: Optional[Dict[str, Any]] = None
    artifacts: Optional[Dict[str, str]] = None

class GCPCalibrationRequest(BaseModel):
    gcps: List[GCPItem]

class CalibrationResult(BaseModel):
    method: str  # "dem", "gcp", "scaled_estimate", "relative"
    is_metric: bool
    scale: float
    offset: float
    r2: Optional[float] = None
    rmse: Optional[float] = None
    mae: Optional[float] = None
    correlation: Optional[float] = None
    valid_pixels: Optional[int] = None
    gcp_count: Optional[int] = None
    confidence: str  # "high", "medium", "estimated", "relative"
    message: str

class DSMStats(BaseModel):
    min_elevation: float
    max_elevation: float
    mean_elevation: float
    median_elevation: float
    std_elevation: float
    relief: float
    average_slope_deg: float
    max_slope_deg: float
    steep_area_pct: float  # slope > 30 deg
    crs: Optional[str] = None
    is_metric: bool

class DisasterRiskStats(BaseModel):
    low_lying_area_pct: float
    steep_slope_hazard_pct: float
    moderate_slope_pct: float
    gentle_slope_pct: float
    ruggedness_index: float
    elevation_thresholds: Dict[str, float]

class MeshMetadata(BaseModel):
    grid_width: int
    grid_height: int
    vertex_count: int
    face_count: int
    heightfield_url: str
    obj_url: str
    quality: str = "high"

class PipelineDimensions(BaseModel):
    input_width: int
    input_height: int
    depth_width: int
    depth_height: int
    dsm_width: int
    dsm_height: int
    render_grid_width: int
    render_grid_height: int
    is_low_resolution: bool = False
    resolution_warning: Optional[str] = None
    interpolation_applied: bool = False
    interpolation_method: Optional[str] = None

class ReconstructionSummary(BaseModel):
    job_id: str
    filename: str
    is_georeferenced: bool
    image_metadata: ImageMetadata
    dem_metadata: Optional[DEMMetadata] = None
    calibration: CalibrationResult
    dsm_stats: DSMStats
    disaster_risk: DisasterRiskStats
    mesh_metadata: MeshMetadata
    assets: Dict[str, str]
    timing_seconds: Dict[str, float]
    device_used: str
    elevation_histogram: Optional[List[Dict[str, Any]]] = None
    dimensions: Optional[PipelineDimensions] = None
    dataset_id: Optional[str] = None

class ValidationStageItem(BaseModel):
    stage_id: str
    name: str
    passed: bool
    warning: bool = False
    message: str

class InputValidationResult(BaseModel):
    status: str  # "ready", "warning", "rejected"
    is_suitable: bool
    suitability_score: int  # 0 - 100
    detected_content: str
    rejection_reason: Optional[str] = None
    dominant_human_detected: bool = False
    stages: List[ValidationStageItem]
    warnings: List[str] = []
    width: int
    height: int
    format: str
    is_georeferenced: bool
    crs: Optional[str] = None

class EvaluationMetrics(BaseModel):
    mae: float
    rmse: float
    pearson_r: float
    mbe: float
    mean_error: float
    median_error: float
    median_abs_error: Optional[float] = None
    max_abs_error: float
    min_error: float
    max_error: float
    r2: Optional[float] = None
    le90: Optional[float] = None
    le95: Optional[float] = None
    sample_count: int
    valid_pixel_count: int
    valid_pixel_pct: Optional[float] = None
    reference_min: float
    reference_max: float
    predicted_min: float
    predicted_max: float
    # Monocular Depth Metrics
    abs_rel: Optional[float] = None
    sq_rel: Optional[float] = None
    delta1: Optional[float] = None
    delta2: Optional[float] = None
    delta3: Optional[float] = None
    # Slope Metrics
    slope_mae: Optional[float] = None
    slope_rmse: Optional[float] = None

class LandscapeMetric(BaseModel):
    landscape_type: str  # "Urban", "Sparse", "Hilly", "Forest" (or "Urban / Flat (<10°)", etc.)
    sample_count: int
    mae: float
    rmse: float
    pearson_r: float
    bias: Optional[float] = None
    median_abs_error: Optional[float] = None
    category_source: Optional[str] = "dataset_label"

class EvaluationConfigRequest(BaseModel):
    profile: Optional[str] = "terrain_standard"
    selected_metrics: Optional[List[str]] = None

class EvaluationResponse(BaseModel):
    job_id: str
    has_evaluation: bool
    metrics: Optional[EvaluationMetrics] = None
    predicted_map_url: Optional[str] = None
    reference_map_url: Optional[str] = None
    error_map_url: Optional[str] = None
    abs_error_map_url: Optional[str] = None
    error_histogram: Optional[List[Dict[str, Any]]] = None
    scatter_samples: Optional[List[Dict[str, float]]] = None
    landscape_evaluation: Optional[List[LandscapeMetric]] = None
    selected_metrics: Optional[List[str]] = None
    profile_name: Optional[str] = None
    reference_filename: Optional[str] = None
    disclaimer: str

class TerrainProfileRequest(BaseModel):
    x1_pct: float
    y1_pct: float
    x2_pct: float
    y2_pct: float
    samples: int = 100

class ProfilePoint(BaseModel):
    distance_m: float
    elevation: float
    slope_deg: float
    x_pct: float
    y_pct: float

class TerrainProfileResponse(BaseModel):
    points: List[ProfilePoint]
    total_distance_m: float
    min_elevation: float
    max_elevation: float
    elevation_gain_m: float
    elevation_loss_m: float

class FloodSimulationRequest(BaseModel):
    water_elevation: float

class FloodSimulationResponse(BaseModel):
    water_elevation: float
    inundated_area_pct: float
    inundated_pixels: int
    total_pixels: int
    flood_mask_url: str
    max_water_depth: float
    mean_water_depth: float
    advisory_notice: str

class DatasetSummary(BaseModel):
    id: str
    name: str
    source: str  # "user_upload" | "preloaded"
    original_filename: str
    file_type: str
    width: int
    height: int
    channels: int = 3
    georeferenced: bool
    crs: Optional[str] = None
    transform: Optional[List[float]] = None
    bounds: Optional[List[float]] = None
    resolution: Optional[List[float]] = None
    nodata: Optional[float] = None
    dtype: Optional[str] = "uint8"
    classification: Optional[str] = None
    is_low_resolution: bool = False
    resolution_warning: Optional[str] = None
    has_dem: bool = False
    dem_metadata: Optional[DEMMetadata] = None
    has_gcps: bool = False
    parsed_gcps: Optional[List[GCPItem]] = None
    created_at: str
    status: str = "ready"  # "ready", "processing", "completed", "failed"
    preview_url: str
    thumbnail_url: str
    active_job_id: Optional[str] = None
    latest_results: Optional[ReconstructionSummary] = None
    input_validation: Optional[InputValidationResult] = None

class DatasetListResponse(BaseModel):
    datasets: List[DatasetSummary]
    active_dataset_id: Optional[str] = None

class ProcessDatasetRequest(BaseModel):
    dataset_id: str
    dem_file: Optional[str] = None
    gcps: Optional[List[GCPItem]] = None


class GeoTIFFVerificationResult(BaseModel):
    is_valid: bool
    filepath: str
    width: int
    height: int
    crs: Optional[str] = None
    transform: Optional[List[float]] = None
    bounds: Optional[List[float]] = None
    resolution: Optional[List[float]] = None
    nodata: Optional[float] = None
    dtype: str
    tags: Dict[str, str] = {}
    crs_preserved: bool
    transform_preserved: bool
    dimensions_preserved: bool
    nodata_preserved: bool
    values_preserved: bool
    max_value_diff: float = 0.0
    message: str


class CreateJobRequest(BaseModel):
    dataset_id: Optional[str] = None
    image_path: Optional[str] = None
    dem_path: Optional[str] = None
    gcp_path: Optional[str] = None
    dem_file: Optional[str] = None
    gcps: Optional[List[GCPItem]] = None

