export interface ImageMetadata {
  width: number;
  height: number;
  format: string;
  datatype?: string;
  classification?: string;
  is_low_resolution?: boolean;
  resolution_warning?: string | null;
  file_size_bytes: number;
  is_georeferenced: boolean;
  crs?: string | null;
  transform?: number[] | null;
  bounds?: [number, number, number, number] | null;
  resolution?: [number, number] | null;
  nodata?: number | null;
  band_count: number;
}

export interface PipelineDimensions {
  input_width: number;
  input_height: number;
  depth_width: number;
  depth_height: number;
  dsm_width: number;
  dsm_height: number;
  render_grid_width: number;
  render_grid_height: number;
  is_low_resolution: boolean;
  resolution_warning?: string | null;
  interpolation_applied: boolean;
  interpolation_method: string;
}

export interface DEMMetadata {
  filename: string;
  crs?: string | null;
  resolution?: [number, number] | null;
  bounds?: [number, number, number, number] | null;
  min_elevation: number;
  max_elevation: number;
  is_compatible: boolean;
  compatibility_note?: string | null;
}

export interface GCPItem {
  id: string | number;
  x: number;
  y: number;
  elevation: number;
}

export interface UploadResponse {
  job_id: string;
  filename: string;
  metadata: ImageMetadata;
  has_dem: boolean;
  dem_metadata?: DEMMetadata | null;
  has_gcp: boolean;
  parsed_gcps?: GCPItem[] | null;
  message: string;
}

export type JobState =
  | 'QUEUED'
  | 'VALIDATING'
  | 'INFERENCE'
  | 'CALIBRATING'
  | 'GENERATING_DSM'
  | 'VALIDATING_RESULT'
  | 'COMPLETED'
  | 'FAILED'
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed';

export interface CentralJobRecord {
  job_id: string;
  status: JobState;
  input: Record<string, any>;
  validation?: InputValidationResult | null;
  depth?: {
    device: string;
    shape: [number, number];
    normalized_range: [number, number];
    array_type: string;
    unit: string;
  } | null;
  calibration?: CalibrationResult | null;
  dsm?: {
    stats: DSMStats;
    disaster_risk: DisasterRiskStats;
    is_metric: boolean;
    crs?: string | null;
    resolution?: [number, number] | null;
    units: string;
  } | null;
  validation_result?: EvaluationResponse | null;
  artifacts: Record<string, string>;
  errors?: string | null;
}

export interface ProcessingStage {
  stage_id: string;
  name: string;
  progress: number;
  message: string;
  is_current: boolean;
  is_done: boolean;
}

export interface JobStatus {
  job_id: string;
  status: JobState;
  current_stage: string;
  progress: number;
  message: string;
  stages: ProcessingStage[];
  error?: string | null;
  errors?: string | null;
  input?: Record<string, any> | null;
  validation?: Record<string, any> | null;
  depth?: Record<string, any> | null;
  calibration?: CalibrationResult | null;
  dsm?: Record<string, any> | null;
  validation_result?: EvaluationResponse | null;
  artifacts?: Record<string, string> | null;
}

export interface CalibrationResult {
  method: 'dem' | 'gcp' | 'scaled_estimate' | 'relative';
  is_metric: boolean;
  scale: number;
  offset: number;
  r2?: number | null;
  rmse?: number | null;
  mae?: number | null;
  correlation?: number | null;
  valid_pixels?: number | null;
  gcp_count?: number | null;
  confidence: 'high' | 'medium' | 'estimated' | 'relative';
  message: string;
}

export interface DSMStats {
  min_elevation: number;
  max_elevation: number;
  mean_elevation: number;
  median_elevation: number;
  std_elevation: number;
  relief: number;
  average_slope_deg: number;
  max_slope_deg: number;
  steep_area_pct: number;
  crs?: string | null;
  is_metric: boolean;
}

export interface DisasterRiskStats {
  low_lying_area_pct: number;
  steep_slope_hazard_pct: number;
  moderate_slope_pct: number;
  gentle_slope_pct: number;
  ruggedness_index: number;
  elevation_thresholds: {
    flood_risk_low_m: number;
    median_elevation_m: number;
    high_ridge_m: number;
  };
}

export interface MeshMetadata {
  grid_width: number;
  grid_height: number;
  vertex_count: number;
  face_count: number;
  heightfield_url: string;
  obj_url: string;
  quality?: string;
}

export interface ReconstructionSummary {
  job_id: string;
  filename: string;
  is_georeferenced: boolean;
  image_metadata: ImageMetadata;
  dem_metadata?: DEMMetadata | null;
  calibration: CalibrationResult;
  dimensions?: PipelineDimensions | null;
  dsm_stats: DSMStats;
  disaster_risk: DisasterRiskStats;
  mesh_metadata: MeshMetadata;
  assets: {
    rgb_texture: string;
    depth_gray: string;
    depth_color: string;
    dsm_geotiff: string;
    slope_geotiff?: string;
    hillshade_geotiff?: string;
    dsm_color: string;
    hillshade: string;
    slope: string;
    contour: string;
    mesh_heightfield: string;
    mesh_obj: string;
  };
  timing_seconds: {
    inference?: number;
    preprocessing?: number;
    calibration?: number;
    mesh_generation?: number;
    total_seconds?: number;
  };
  device_used: string;
  elevation_histogram?: Array<{
    bin_start: number;
    bin_end: number;
    bin_label: string;
    count: number;
    percentage: number;
  }>;
  dataset_id?: string | null;
}

export interface HeightfieldData {
  quality?: string;
  grid_width: number;
  grid_height: number;
  data_width?: number;
  data_height?: number;
  is_upsampled?: boolean;
  interpolation_method?: string;
  world_x_span: number;
  world_z_span: number;
  min_elevation: number;
  max_elevation: number;
  relief: number;
  heights: number[];
  raw_elevations: number[];
  reference_elevations?: (number | null)[] | null;
  elevation_errors?: (number | null)[] | null;
}

export interface PointInspectionData {
  pixelCoords: { x: number; y: number };
  geoCoords?: { x: number; y: number; lat?: number; lon?: number } | null;
  predictedHeight: number;
  referenceHeight: number | null;
  error: number | null;
  slopeDeg: number;
  worldPos: [number, number, number];
  isMetric: boolean;
}

export interface ValidationStageItem {
  stage_id: string;
  name: string;
  passed: boolean;
  warning?: boolean;
  message: string;
}

export interface InputValidationResult {
  status: 'ready' | 'warning' | 'rejected';
  is_suitable: boolean;
  suitability_score: number;
  detected_content: string;
  rejection_reason?: string | null;
  dominant_human_detected?: boolean;
  stages: ValidationStageItem[];
  warnings?: string[];
  width: number;
  height: number;
  format: string;
  is_georeferenced: boolean;
  crs?: string | null;
}

export interface LandscapeMetric {
  landscape_type: string;
  sample_count: number;
  mae: number;
  rmse: number;
  pearson_r: number;
  bias?: number | null;
  median_abs_error?: number | null;
  category_source?: string | null;
}

export interface EvaluationMetrics {
  mae: number;
  rmse: number;
  pearson_r: number;
  mbe: number;
  mean_error: number;
  median_error: number;
  median_abs_error?: number | null;
  max_abs_error: number;
  min_error: number;
  max_error: number;
  r2?: number | null;
  le90?: number | null;
  le95?: number | null;
  sample_count: number;
  valid_pixel_count: number;
  valid_pixel_pct?: number | null;
  reference_min: number;
  reference_max: number;
  predicted_min: number;
  predicted_max: number;
  // Monocular depth benchmark
  abs_rel?: number | null;
  sq_rel?: number | null;
  delta1?: number | null;
  delta2?: number | null;
  delta3?: number | null;
  // Slope metrics
  slope_mae?: number | null;
  slope_rmse?: number | null;
}

export interface EvaluationConfigRequest {
  profile?: string;
  selected_metrics?: string[];
}

export interface EvaluationResponse {
  job_id: string;
  has_evaluation: boolean;
  metrics?: EvaluationMetrics | null;
  predicted_map_url?: string | null;
  reference_map_url?: string | null;
  error_map_url?: string | null;
  abs_error_map_url?: string | null;
  error_histogram?: Array<{
    bin_start: number;
    bin_end: number;
    bin_label: string;
    count: number;
    percentage: number;
  }> | null;
  scatter_samples?: Array<{
    reference: number;
    predicted: number;
    error: number;
  }> | null;
  landscape_evaluation?: LandscapeMetric[] | null;
  selected_metrics?: string[] | null;
  profile_name?: string | null;
  reference_filename?: string | null;
  disclaimer: string;
}

export interface PointInspectionResult {
  job_id: string;
  pixel_coords: { x: number; y: number };
  geo_coords?: { x: number; y: number; lat?: number; lon?: number } | null;
  predicted_height: number;
  reference_height?: number | null;
  error?: number | null;
  slope_deg: number;
  is_metric: boolean;
  unit: string;
}

export interface SampleDataset {
  id: string;
  title: string;
  description: string;
  type: 'georeferenced' | 'non_georeferenced';
  format: string;
  has_dem: boolean;
  has_gcps: boolean;
  image_file: string;
  dem_file?: string | null;
  gcp_file?: string | null;
}

export interface ProfilePoint {
  distance_m: number;
  elevation: number;
  slope_deg: number;
  x_pct: number;
  y_pct: number;
}

export interface TerrainProfileResponse {
  points: ProfilePoint[];
  total_distance_m: number;
  min_elevation: number;
  max_elevation: number;
  elevation_gain_m: number;
  elevation_loss_m: number;
}

export interface FloodSimulationResponse {
  water_elevation: number;
  inundated_area_pct: number;
  inundated_pixels: number;
  total_pixels: number;
  flood_mask_url: string;
  max_water_depth: number;
  mean_water_depth: number;
  advisory_notice: string;
}

export interface DatasetSummary {
  id: string;
  name: string;
  source: 'user_upload' | 'preloaded';
  original_filename: string;
  file_type: string;
  width: number;
  height: number;
  channels: number;
  georeferenced: boolean;
  crs?: string | null;
  transform?: number[] | null;
  bounds?: [number, number, number, number] | null;
  resolution?: [number, number] | null;
  nodata?: number | null;
  dtype?: string;
  classification?: string;
  is_low_resolution: boolean;
  resolution_warning?: string | null;
  has_dem: boolean;
  dem_metadata?: DEMMetadata | null;
  has_gcps: boolean;
  parsed_gcps?: GCPItem[] | null;
  created_at: string;
  status: 'ready' | 'processing' | 'completed' | 'failed' | 'rejected';
  preview_url: string;
  thumbnail_url: string;
  active_job_id?: string | null;
  latest_results?: ReconstructionSummary | null;
  input_validation?: InputValidationResult | null;
}

export interface DatasetListResponse {
  datasets: DatasetSummary[];
  active_dataset_id?: string | null;
}
