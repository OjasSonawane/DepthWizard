import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
from PIL import Image
import rasterio

from app.config import settings
from app.models.depth_model import DepthEstimator
from app.services.geospatial_service import GeospatialService
from app.services.calibration_service import CalibrationService
from app.services.dsm_service import DSMService
from app.services.mesh_service import MeshService
from app.services.evaluation_service import EvaluationService
from app.schemas.schemas import (
    JobStatus, ProcessingStage, ReconstructionSummary, ImageMetadata,
    DEMMetadata, CalibrationResult, DSMStats, DisasterRiskStats, MeshMetadata,
    EvaluationResponse, TerrainProfileResponse, ProfilePoint,
    FloodSimulationResponse, GCPItem, LandscapeMetric, PipelineDimensions
)

logger = logging.getLogger("depthwizard.pipeline")

# Standardized 8 operational stages for ISRO Disaster Management Pipeline
STAGES_DEFINITION = [
    ("validate_input", "01 Image Validation", 10),
    ("extract_metadata", "02 Metadata Extraction", 22),
    ("estimate_depth", "03 Depth Estimation", 42),
    ("calibrate_scale", "04 Scale Calibration", 58),
    ("generate_dsm", "05 DSM Generation", 72),
    ("build_mesh", "06 Terrain Mesh", 85),
    ("render_visualizations", "07 Texture Projection", 94),
    ("finalize", "08 Analysis Ready", 100),
]

class PipelineManager:
    _instance: Optional["PipelineManager"] = None

    def __init__(self):
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.depth_model = DepthEstimator.get_instance()
        self._load_saved_jobs()

    @classmethod
    def get_instance(cls) -> "PipelineManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_saved_jobs(self):
        jobs_file = settings.STORAGE_DIR / "jobs.json"
        if jobs_file.exists():
            try:
                with open(jobs_file, "r") as f:
                    self.jobs = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load jobs cache: {e}")

    def _save_jobs(self):
        jobs_file = settings.STORAGE_DIR / "jobs.json"
        try:
            with open(jobs_file, "w") as f:
                json.dump(self.jobs, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not persist jobs cache: {e}")

    def register_job(
        self,
        job_id: str,
        image_path: Any,
        metadata: ImageMetadata,
        dem_path: Optional[Any] = None,
        gcp_path: Optional[Any] = None,
        dem_metadata: Optional[DEMMetadata] = None,
        dataset_id: Optional[str] = None
    ) -> JobStatus:
        image_path = Path(image_path)
        dem_path = Path(dem_path) if dem_path else None
        gcp_path = Path(gcp_path) if gcp_path else None

        stages = [
            ProcessingStage(
                stage_id=s_id,
                name=name,
                progress=prog,
                message="Pending...",
                is_current=False,
                is_done=False
            )
            for s_id, name, prog in STAGES_DEFINITION
        ]

        input_data = {
            "image_path": str(image_path),
            "filename": image_path.name,
            "width": metadata.width,
            "height": metadata.height,
            "format": metadata.format,
            "is_georeferenced": metadata.is_georeferenced,
            "crs": metadata.crs,
            "bounds": metadata.bounds,
            "resolution": metadata.resolution,
            "nodata": metadata.nodata,
            "band_count": metadata.band_count,
            "file_hash": metadata.file_hash,
            "dem_path": str(dem_path) if dem_path else None,
            "gcp_path": str(gcp_path) if gcp_path else None
        }

        self.jobs[job_id] = {
            "job_id": job_id,
            "dataset_id": dataset_id,
            "status": "QUEUED",
            "current_stage": "validate_input",
            "progress": 0,
            "message": "Queued for reconstruction",
            "stages": [s.model_dump() for s in stages],
            "image_path": str(image_path),
            "dem_path": str(dem_path) if dem_path else None,
            "gcp_path": str(gcp_path) if gcp_path else None,
            "dem_metadata": dem_metadata.model_dump() if dem_metadata else None,
            "metadata": metadata.model_dump(),
            "input": input_data,
            "validation": None,
            "depth": None,
            "calibration": None,
            "dsm": None,
            "validation_result": None,
            "artifacts": {},
            "results": None,
            "elevation_histogram": None,
            "evaluation": None,
            "error": None,
            "errors": None
        }
        self._save_jobs()
        return self.get_job_status(job_id)

    def get_job_status(self, job_id: str) -> JobStatus:
        if job_id not in self.jobs:
            raise KeyError(f"Job {job_id} not found.")
        job = self.jobs[job_id]
        return JobStatus(
            job_id=job["job_id"],
            status=job["status"],
            current_stage=job.get("current_stage", "validate_input"),
            progress=job.get("progress", 0),
            message=job.get("message", ""),
            stages=[ProcessingStage(**s) for s in job.get("stages", [])],
            error=job.get("error"),
            errors=job.get("errors") or job.get("error"),
            input=job.get("input"),
            validation=job.get("validation"),
            depth=job.get("depth"),
            calibration=job.get("calibration"),
            dsm=job.get("dsm"),
            validation_result=job.get("validation_result") or job.get("evaluation"),
            artifacts=job.get("artifacts") or {}
        )

    def _update_stage(self, job_id: str, stage_id: str, msg: str, progress: int):
        job = self.jobs[job_id]
        job["current_stage"] = stage_id
        job["progress"] = progress
        job["message"] = msg
        for s in job.get("stages", []):
            if s["stage_id"] == stage_id:
                s["is_current"] = True
                s["is_done"] = False
                s["message"] = msg
            elif s["progress"] < progress:
                s["is_current"] = False
                s["is_done"] = True
        self._save_jobs()

    def run_pipeline(self, job_id: str) -> ReconstructionSummary:
        job = self.jobs[job_id]
        active_statuses = {"VALIDATING", "INFERENCE", "CALIBRATING", "GENERATING_DSM", "VALIDATING_RESULT"}
        if job.get("status") in active_statuses:
            raise RuntimeError(f"Job {job_id} is already actively processing (current status: {job['status']}).")
        
        job["status"] = "VALIDATING"
        start_time = time.time()
        timings = {}
        if "artifacts" not in job or job["artifacts"] is None:
            job["artifacts"] = {}

        try:
            image_path = Path(job["image_path"])
            dem_path = Path(job["dem_path"]) if job.get("dem_path") else None
            gcp_path = Path(job["gcp_path"]) if job.get("gcp_path") else None

            # 01 Image Validation & Metadata Extraction (VALIDATING)
            job["status"] = "VALIDATING"
            self._update_stage(job_id, "validate_input", "Validating imagery integrity & optical suitability...", 10)
            if not image_path.exists():
                raise FileNotFoundError(f"Image {image_path} not found.")

            # Validate optical suitability
            try:
                from app.services.image_validator import ImageValidator
                val_result = ImageValidator.validate_image(image_path)
                job["validation"] = val_result.model_dump()
                if val_result.status == "rejected":
                    if job.get("errors") is None:
                        job["errors"] = []
                    job["errors"].append(f"Validation rejection notice: {val_result.rejection_reason}")
            except Exception as e_val:
                logger.warning(f"Image validation check notice: {e_val}")

            # 02 Metadata Extraction
            t0 = time.time()
            self._update_stage(job_id, "extract_metadata", "Extracting CRS, affine transform, and geospatial tags...", 22)
            meta, rgb_array = GeospatialService.inspect_file(image_path)
            timings["preprocessing"] = round(time.time() - t0, 3)

            # Update job input metadata with inspected info
            if "input" in job and job["input"]:
                job["input"]["width"] = meta.width
                job["input"]["height"] = meta.height
                job["input"]["crs"] = meta.crs
                job["input"]["is_georeferenced"] = meta.is_georeferenced
                job["input"]["bounds"] = meta.bounds
                job["input"]["resolution"] = meta.resolution

            # Save texture for Three.js
            texture_filename = f"{job_id}_texture.jpg"
            texture_path = settings.STORAGE_DIR / "uploads" / texture_filename
            Image.fromarray(rgb_array).save(texture_path, quality=90)
            job["artifacts"]["rgb_texture"] = f"/storage/uploads/{texture_filename}"

            # 03 Depth Estimation (INFERENCE)
            job["status"] = "INFERENCE"
            t0 = time.time()
            self._update_stage(job_id, "estimate_depth", f"Executing monocular depth model on {self.depth_model.device.upper()}...", 42)
            relative_depth = self.depth_model.predict(rgb_array)
            norm_depth = self.depth_model.normalize_depth(relative_depth)
            timings["inference"] = round(time.time() - t0, 3)

            job["depth"] = {
                "device": self.depth_model.device.upper(),
                "shape": [int(norm_depth.shape[0]), int(norm_depth.shape[1])],
                "normalized_range": [0.0, 1.0],
                "array_type": "float32",
                "unit": "relative"
            }

            # 04 Scale Calibration (CALIBRATING)
            job["status"] = "CALIBRATING"
            t0 = time.time()
            self._update_stage(job_id, "calibrate_scale", "Calibrating scale (DEM / GCP / Relative)...", 58)
            
            calib_result: CalibrationResult
            dsm: np.ndarray
            ref_dem_matched: Optional[np.ndarray] = None

            if not meta.is_georeferenced:
                # Non-georeferenced -> rDSM
                dsm, calib_result = CalibrationService.calibrate_relative(norm_depth)
            elif dem_path and dem_path.exists():
                # Georeferenced with DEM
                try:
                    ref_dem = GeospatialService.reproject_match(
                        reference_path=dem_path,
                        target_shape=norm_depth.shape,
                        target_crs_str=meta.crs,
                        target_transform_list=meta.transform
                    )
                    ref_dem_matched = ref_dem
                    dsm, calib_result = CalibrationService.calibrate_with_dem(norm_depth, ref_dem)
                except Exception as ex_dem:
                    logger.warning(f"DEM co-registration failed ({ex_dem}), using scaled estimate")
                    dsm, calib_result = CalibrationService.calibrate_scaled_estimate(norm_depth)
            elif gcp_path and gcp_path.exists():
                # Georeferenced with GCPs
                try:
                    gcps = self._parse_gcp_csv(gcp_path)
                    dsm, calib_result = CalibrationService.calibrate_with_gcps(
                        norm_depth, gcps, meta.transform, crs_str=meta.crs
                    )
                except Exception as ex_gcp:
                    logger.warning(f"GCP calibration failed ({ex_gcp}), using scaled estimate")
                    dsm, calib_result = CalibrationService.calibrate_scaled_estimate(norm_depth)
            else:
                # Georeferenced without DEM/GCP -> scaled estimate
                dsm, calib_result = CalibrationService.calibrate_scaled_estimate(norm_depth)

            timings["calibration"] = round(time.time() - t0, 3)
            job["calibration"] = calib_result.model_dump()

            # 05 DSM Generation (GENERATING_DSM)
            job["status"] = "GENERATING_DSM"
            self._update_stage(job_id, "generate_dsm", "Writing DSM GeoTIFF and slope derivatives...", 72)
            dsm_geotiff_path = settings.DSM_DIR / f"{job_id}_dsm.tif"

            dsm_meta_tags = {
                "INPUT_FILENAME": job.get("filename", image_path.name),
                "INPUT_HASH": meta.file_hash or "",
                "CRS": meta.crs or "NONE",
                "RESOLUTION": f"{meta.resolution[0]},{meta.resolution[1]}" if meta.resolution else "1.0,1.0",
                "MODEL": settings.MODEL_NAME,
                "MODEL_VERSION": settings.VERSION,
                "CALIBRATION_METHOD": calib_result.method,
                "REFERENCE_SOURCE": dem_path.name if dem_path and dem_path.exists() else ("GCP_CSV" if gcp_path and gcp_path.exists() else "NONE"),
                "ELEVATION_UNITS": "meters" if calib_result.is_metric else "relative",
                "PIPELINE_VERSION": settings.VERSION,
                "TIMESTAMP": datetime.now(timezone.utc).isoformat()
            }

            GeospatialService.save_geotiff(
                output_path=dsm_geotiff_path,
                data=dsm,
                crs_str=meta.crs if meta.is_georeferenced else None,
                transform_list=meta.transform if meta.is_georeferenced else None,
                metadata_tags=dsm_meta_tags
            )

            np.save(settings.DSM_DIR / f"{job_id}_dsm.npy", dsm.astype(np.float32))
            np.save(settings.DEPTH_DIR / f"{job_id}_depth.npy", norm_depth.astype(np.float32))

            ground_res = GeospatialService.get_ground_resolution_meters(
                resolution=tuple(meta.resolution) if meta.resolution else (1.0, 1.0),
                crs_str=meta.crs,
                bounds=meta.bounds
            )
            slope_deg, hillshade = DSMService.compute_slope_and_hillshade(
                dsm=dsm,
                resolution=ground_res
            )
            np.save(settings.DSM_DIR / f"{job_id}_slope.npy", slope_deg.astype(np.float32))

            if meta.is_georeferenced:
                slope_geotiff_path = settings.DSM_DIR / f"{job_id}_slope.tif"
                slope_tags = {**dsm_meta_tags, "VARIABLE": "SLOPE_DEGREES", "ELEVATION_UNITS": "degrees"}
                GeospatialService.save_geotiff(
                    output_path=slope_geotiff_path,
                    data=slope_deg,
                    crs_str=meta.crs,
                    transform_list=meta.transform,
                    metadata_tags=slope_tags
                )
                hillshade_geotiff_path = settings.DSM_DIR / f"{job_id}_hillshade.tif"
                hs_tags = {**dsm_meta_tags, "VARIABLE": "HILLSHADE_ILLUMINATION", "ELEVATION_UNITS": "uint8"}
                GeospatialService.save_geotiff(
                    output_path=hillshade_geotiff_path,
                    data=hillshade,
                    crs_str=meta.crs,
                    transform_list=meta.transform,
                    metadata_tags=hs_tags
                )

            # 06 Terrain Mesh (multi-LOD)
            t0 = time.time()
            self._update_stage(job_id, "build_mesh", "Constructing 3D terrain heightfield & Wavefront OBJ...", 85)
            mesh_prefix = settings.MESH_DIR / job_id
            mesh_meta, json_path, obj_path = MeshService.generate_mesh_assets(
                dsm=dsm,
                output_prefix=mesh_prefix,
                quality="high",
                grid_dim=192,
                reference_dsm=ref_dem_matched
            )
            # Pre-generate low (64x64) and medium (128x128) LODs as well
            MeshService.generate_mesh_assets(dsm=dsm, output_prefix=mesh_prefix, quality="low", grid_dim=64, reference_dsm=ref_dem_matched)
            MeshService.generate_mesh_assets(dsm=dsm, output_prefix=mesh_prefix, quality="medium", grid_dim=128, reference_dsm=ref_dem_matched)
            timings["mesh_generation"] = round(time.time() - t0, 3)

            # 07 Texture Projection & Visualizations
            self._update_stage(job_id, "render_visualizations", "Rendering colorized telemetry layers...", 94)
            vis_prefix = settings.STORAGE_DIR / "depth" / job_id
            rendered_maps = DSMService.render_colorized_maps(
                dsm=dsm,
                relative_depth=norm_depth,
                slope_deg=slope_deg,
                hillshade=hillshade,
                output_prefix=vis_prefix
            )

            # Statistics & Risk
            dsm_stats, risk_stats, hist_data = DSMService.compute_dsm_stats(
                dsm=dsm,
                slope_deg=slope_deg,
                crs_str=meta.crs,
                is_metric=calib_result.is_metric
            )
            job["elevation_histogram"] = hist_data

            job["dsm"] = {
                "stats": dsm_stats.model_dump(),
                "disaster_risk": risk_stats.model_dump(),
                "is_metric": calib_result.is_metric,
                "crs": meta.crs,
                "resolution": meta.resolution,
                "units": "meters" if calib_result.is_metric else "relative"
            }

            # Construct separate pipeline dimensions metadata
            is_upsampled = bool(mesh_meta.grid_width > dsm.shape[1] or mesh_meta.grid_height > dsm.shape[0])
            dimensions = PipelineDimensions(
                input_width=meta.width,
                input_height=meta.height,
                depth_width=int(norm_depth.shape[1]),
                depth_height=int(norm_depth.shape[0]),
                dsm_width=int(dsm.shape[1]),
                dsm_height=int(dsm.shape[0]),
                render_grid_width=mesh_meta.grid_width,
                render_grid_height=mesh_meta.grid_height,
                is_low_resolution=meta.is_low_resolution,
                resolution_warning=meta.resolution_warning,
                interpolation_applied=is_upsampled,
                interpolation_method="bicubic" if is_upsampled else "area_decimation"
            )

            assets = {
                "rgb_texture": f"/storage/uploads/{texture_filename}",
                "depth_gray": f"/storage/depth/{rendered_maps['depth_gray'].name}",
                "depth_color": f"/storage/depth/{rendered_maps['depth_color'].name}",
                "dsm_geotiff": f"/storage/dsm/{dsm_geotiff_path.name}",
                "dsm_color": f"/storage/depth/{rendered_maps['dsm_color'].name}",
                "hillshade": f"/storage/depth/{rendered_maps['hillshade'].name}",
                "slope": f"/storage/depth/{rendered_maps['slope'].name}",
                "contour": f"/storage/depth/{rendered_maps['contour'].name}",
                "mesh_heightfield": f"/storage/meshes/{json_path.name}",
                "mesh_obj": f"/storage/meshes/{obj_path.name}"
            }
            if meta.is_georeferenced:
                assets["slope_geotiff"] = f"/storage/dsm/{job_id}_slope.tif"
                assets["hillshade_geotiff"] = f"/storage/dsm/{job_id}_hillshade.tif"

            job["artifacts"].update(assets)

            mesh_meta.heightfield_url = assets["mesh_heightfield"]
            mesh_meta.obj_url = assets["mesh_obj"]

            dem_meta_obj = DEMMetadata(**job["dem_metadata"]) if job.get("dem_metadata") else None

            # 08 Evaluation against reference if provided (VALIDATING_RESULT)
            job["status"] = "VALIDATING_RESULT"
            if dem_path and dem_path.exists():
                try:
                    eval_res = self.evaluate(job_id=job_id, ref_file_path=dem_path)
                    job["validation_result"] = eval_res.model_dump()
                except Exception as ex_eval:
                    logger.warning(f"Auto-validation against reference DEM skipped/failed: {ex_eval}")
                    job["validation_result"] = None
            else:
                job["validation_result"] = None

            # 09 Finalize & Summary (COMPLETED)
            self._update_stage(job_id, "finalize", "Reconstruction complete. Initializing 3D Explorer...", 100)
            timings["total_seconds"] = round(time.time() - start_time, 2)

            summary = ReconstructionSummary(
                job_id=job_id,
                filename=image_path.name,
                is_georeferenced=meta.is_georeferenced,
                image_metadata=meta,
                dem_metadata=dem_meta_obj,
                calibration=calib_result,
                dimensions=dimensions,
                dsm_stats=dsm_stats,
                disaster_risk=risk_stats,
                mesh_metadata=mesh_meta,
                assets=assets,
                timing_seconds=timings,
                device_used=self.depth_model.device.upper(),
                elevation_histogram=hist_data,
                dataset_id=job.get("dataset_id")
            )

            job["status"] = "COMPLETED"
            job["current_stage"] = "finalize"
            job["progress"] = 100
            job["message"] = "Reconstruction completed successfully."
            job["results"] = summary.model_dump()
            
            for s in job.get("stages", []):
                s["is_done"] = True
                s["is_current"] = False

            if job.get("dataset_id"):
                try:
                    from app.services.dataset_service import DatasetService
                    DatasetService.get_instance().update_dataset_job(job["dataset_id"], job_id, summary)
                except Exception as ex_ds:
                    logger.warning(f"Could not link job {job_id} to dataset {job.get('dataset_id')}: {ex_ds}")

            self._save_jobs()
            return summary

        except Exception as e:
            logger.error(f"Pipeline failed for job {job_id}: {e}", exc_info=True)
            job["status"] = "FAILED"
            job["error"] = str(e)
            job["errors"] = str(e)
            job["message"] = f"Error during {job.get('current_stage', 'processing')}: {str(e)}"
            self._save_jobs()
            raise

    def get_results(self, job_id: str) -> ReconstructionSummary:
        if job_id not in self.jobs:
            raise KeyError(f"Job {job_id} not found.")
        job = self.jobs[job_id]
        if not job.get("results"):
            raise ValueError(f"Job {job_id} has not completed yet (status: {job['status']}).")
        return ReconstructionSummary(**job["results"])

    def evaluate(
        self,
        job_id: str,
        ref_file_path: Path,
        profile: Optional[str] = "terrain_standard",
        selected_metrics: Optional[List[str]] = None
    ) -> EvaluationResponse:
        job = self.jobs[job_id]
        dsm_npy_path = settings.DSM_DIR / f"{job_id}_dsm.npy"
        if not dsm_npy_path.exists():
            raise FileNotFoundError("Reconstructed DSM not found. Complete processing first.")

        pred_dsm = np.load(dsm_npy_path)

        # Retrieve job spatial metadata if available
        job_meta = job.get("metadata", {})
        job_crs = job_meta.get("crs")
        job_transform = job_meta.get("transform")
        if not job_crs and "results" in job and "dsm_stats" in job["results"]:
            job_crs = job["results"]["dsm_stats"].get("crs")

        ref_dsm = None
        if ref_file_path.suffix.lower() in [".tif", ".tiff"] and job_crs and job_transform:
            try:
                ref_dsm = GeospatialService.reproject_match(
                    reference_path=ref_file_path,
                    target_shape=pred_dsm.shape,
                    target_crs_str=job_crs,
                    target_transform_list=job_transform
                )
            except Exception as e_reproj:
                logger.warning(f"Reference DEM reprojection failed ({e_reproj}), reading directly")

        if ref_dsm is None:
            if ref_file_path.suffix.lower() == ".npy":
                ref_dsm = np.load(ref_file_path).astype(np.float32)
            elif ref_file_path.suffix.lower() in [".tif", ".tiff"]:
                with rasterio.open(ref_file_path) as src:
                    ref_dsm = src.read(1).astype(np.float32)
                    nodata = src.nodata
                    if nodata is not None:
                        ref_dsm[ref_dsm == nodata] = np.nan
            else:
                ref_meta, ref_array = GeospatialService.inspect_file(ref_file_path)
                if ref_array.ndim == 3:
                    ref_dsm = cv2.cvtColor(ref_array, cv2.COLOR_RGB2GRAY).astype(np.float32)
                else:
                    ref_dsm = ref_array.astype(np.float32)

        output_prefix = settings.STORAGE_DIR / "exports" / job_id
        output_prefix.parent.mkdir(parents=True, exist_ok=True)
        metrics, error_map_path, abs_error_map_path, pred_map_path, ref_map_path, histogram_data, scatter_points, landscape_results, active_metrics, prof_name = EvaluationService.evaluate_against_reference(
            predicted_dsm=pred_dsm,
            reference_dsm=ref_dsm,
            output_prefix=output_prefix,
            profile=profile,
            selected_metrics=selected_metrics,
            crs=job_crs,
            transform=job_transform,
            strata_labels=job.get("strata_labels") or job.get("strata_masks")
        )

        resp = EvaluationResponse(
            job_id=job_id,
            has_evaluation=True,
            metrics=metrics,
            predicted_map_url=f"/storage/exports/{pred_map_path.name}",
            reference_map_url=f"/storage/exports/{ref_map_path.name}",
            error_map_url=f"/storage/exports/{error_map_path.name}",
            abs_error_map_url=f"/storage/exports/{abs_error_map_path.name}",
            error_histogram=histogram_data,
            scatter_samples=scatter_points,
            landscape_evaluation=landscape_results,
            selected_metrics=active_metrics,
            profile_name=prof_name,
            reference_filename=ref_file_path.name,
            disclaimer="Evaluation derived strictly against provided reference elevation raster."
        )

        job["ref_file_path"] = str(ref_file_path)
        job["evaluation"] = resp.model_dump()
        job["validation_result"] = resp.model_dump()
        if "artifacts" in job and isinstance(job["artifacts"], dict):
            if resp.predicted_map_url:
                job["artifacts"]["predicted_map"] = resp.predicted_map_url
            if resp.reference_map_url:
                job["artifacts"]["reference_map"] = resp.reference_map_url
            if resp.error_map_url:
                job["artifacts"]["error_map"] = resp.error_map_url
            if resp.abs_error_map_url:
                job["artifacts"]["abs_error_map"] = resp.abs_error_map_url

        # Refresh 3D terrain heightfield with reference DEM paired values
        try:
            mesh_prefix = settings.MESH_DIR / job_id
            MeshService.generate_mesh_assets(dsm=pred_dsm, output_prefix=mesh_prefix, quality="high", grid_dim=192, reference_dsm=ref_dsm)
            MeshService.generate_mesh_assets(dsm=pred_dsm, output_prefix=mesh_prefix, quality="low", grid_dim=64, reference_dsm=ref_dsm)
            MeshService.generate_mesh_assets(dsm=pred_dsm, output_prefix=mesh_prefix, quality="medium", grid_dim=128, reference_dsm=ref_dsm)
        except Exception as ex_m:
            logger.warning(f"Could not refresh 3D mesh with reference DEM: {ex_m}")

        self._save_jobs()
        return resp

    def get_artifacts(self, job_id: str) -> Dict[str, str]:
        if job_id not in self.jobs:
            raise KeyError(f"Job {job_id} not found.")
        job = self.jobs[job_id]
        artifacts = dict(job.get("artifacts") or {})
        if job.get("results") and "assets" in job["results"]:
            for k, v in job["results"]["assets"].items():
                if k not in artifacts:
                    artifacts[k] = v
        if job.get("evaluation"):
            ev = job["evaluation"]
            if ev.get("predicted_map_url"):
                artifacts["predicted_map"] = ev["predicted_map_url"]
            if ev.get("reference_map_url"):
                artifacts["reference_map"] = ev["reference_map_url"]
            if ev.get("error_map_url"):
                artifacts["error_map"] = ev["error_map_url"]
            if ev.get("abs_error_map_url"):
                artifacts["abs_error_map"] = ev["abs_error_map_url"]
        return artifacts

    def configure_evaluation(
        self,
        job_id: str,
        profile: Optional[str] = "terrain_standard",
        selected_metrics: Optional[List[str]] = None
    ) -> EvaluationResponse:
        if job_id not in self.jobs:
            raise KeyError(f"Job {job_id} not found.")
        job = self.jobs[job_id]
        ref_path_str = job.get("ref_file_path")
        if not ref_path_str or not Path(ref_path_str).exists():
            raise ValueError("No reference dataset found for this job. Please upload a reference DEM first.")
        
        return self.evaluate(
            job_id=job_id,
            ref_file_path=Path(ref_path_str),
            profile=profile,
            selected_metrics=selected_metrics
        )

    def get_evaluation(self, job_id: str) -> EvaluationResponse:
        if job_id not in self.jobs:
            raise KeyError(f"Job {job_id} not found.")
        job = self.jobs[job_id]
        if job.get("evaluation"):
            return EvaluationResponse(**job["evaluation"])
        return EvaluationResponse(
            job_id=job_id,
            has_evaluation=False,
            disclaimer="Validation unavailable — upload a reference elevation dataset."
        )

    def compute_terrain_profile(
        self,
        job_id: str,
        x1_pct: float,
        y1_pct: float,
        x2_pct: float,
        y2_pct: float,
        samples: int = 100
    ) -> TerrainProfileResponse:
        dsm_path = settings.DSM_DIR / f"{job_id}_dsm.npy"
        slope_path = settings.DSM_DIR / f"{job_id}_slope.npy"
        if not dsm_path.exists():
            raise FileNotFoundError("DSM not available.")

        dsm = np.load(dsm_path)
        slope = np.load(slope_path) if slope_path.exists() else np.zeros_like(dsm)
        h, w = dsm.shape

        col1, row1 = x1_pct * (w - 1), y1_pct * (h - 1)
        col2, row2 = x2_pct * (w - 1), y2_pct * (h - 1)

        cols = np.linspace(col1, col2, samples)
        rows = np.linspace(row1, row2, samples)

        job = self.jobs[job_id]
        res = job.get("results", {}).get("image_metadata", {}).get("resolution")
        cell_size = res[0] if res and res[0] else 1.0

        pixel_dist = np.hypot(col2 - col1, row2 - row1)
        total_dist_m = pixel_dist * cell_size

        points: List[ProfilePoint] = []
        elevations = []

        for i in range(samples):
            r = int(np.clip(round(rows[i]), 0, h - 1))
            c = int(np.clip(round(cols[i]), 0, w - 1))
            elev = float(dsm[r, c])
            sl = float(slope[r, c])
            elevations.append(elev)
            dist_m = (i / (samples - 1)) * total_dist_m
            points.append(ProfilePoint(
                distance_m=round(dist_m, 1),
                elevation=round(elev, 2),
                slope_deg=round(sl, 1),
                x_pct=round(cols[i] / (w - 1), 3),
                y_pct=round(rows[i] / (h - 1), 3)
            ))

        elev_diffs = np.diff(elevations)
        gain = float(np.sum(elev_diffs[elev_diffs > 0])) if len(elev_diffs) > 0 else 0.0
        loss = float(np.abs(np.sum(elev_diffs[elev_diffs < 0]))) if len(elev_diffs) > 0 else 0.0

        return TerrainProfileResponse(
            points=points,
            total_distance_m=round(total_dist_m, 1),
            min_elevation=round(float(np.min(elevations)), 2),
            max_elevation=round(float(np.max(elevations)), 2),
            elevation_gain_m=round(gain, 1),
            elevation_loss_m=round(loss, 1)
        )

    def simulate_flood(self, job_id: str, water_elevation: float) -> FloodSimulationResponse:
        dsm_path = settings.DSM_DIR / f"{job_id}_dsm.npy"
        if not dsm_path.exists():
            raise FileNotFoundError("DSM not available.")

        dsm = np.load(dsm_path)
        valid = np.isfinite(dsm) & (dsm > -9000.0)
        total_valid = int(np.count_nonzero(valid))

        flooded_mask = valid & (dsm <= water_elevation)
        flooded_count = int(np.count_nonzero(flooded_mask))
        flooded_pct = (flooded_count / total_valid * 100.0) if total_valid > 0 else 0.0

        water_depths = water_elevation - dsm[flooded_mask]
        max_depth = float(np.max(water_depths)) if len(water_depths) > 0 else 0.0
        mean_depth = float(np.mean(water_depths)) if len(water_depths) > 0 else 0.0

        h, w = dsm.shape
        overlay = np.zeros((h, w, 4), dtype=np.uint8)
        overlay[flooded_mask] = [30, 144, 255, 180]

        mask_name = f"{job_id}_flood_{int(water_elevation)}m.png"
        mask_path = settings.STORAGE_DIR / "depth" / mask_name
        Image.fromarray(overlay, mode="RGBA").save(mask_path)

        return FloodSimulationResponse(
            water_elevation=round(water_elevation, 2),
            inundated_area_pct=round(flooded_pct, 2),
            inundated_pixels=flooded_count,
            total_pixels=total_valid,
            flood_mask_url=f"/storage/depth/{mask_name}",
            max_water_depth=round(max_depth, 2),
            mean_water_depth=round(mean_depth, 2),
            advisory_notice="Illustrative elevation-threshold visualization — not a hydrological flood forecast."
        )

    def _parse_gcp_csv(self, gcp_path: Path) -> List[GCPItem]:
        gcps = []
        with open(gcp_path, "r") as f:
            lines = [l.strip() for l in f.readlines() if l.strip() and not l.startswith("#")]
        
        header = [h.strip().lower() for h in lines[0].split(",")]
        id_idx, x_idx, y_idx, elev_idx = 0, 1, 2, 3

        for i, h in enumerate(header):
            if h in ["id", "point_id", "gcp"]:
                id_idx = i
            elif h in ["x", "lon", "longitude", "easting"]:
                x_idx = i
            elif h in ["y", "lat", "latitude", "northing"]:
                y_idx = i
            elif h in ["z", "elevation", "height", "elev"]:
                elev_idx = i

        for line in lines[1:]:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                try:
                    gcps.append(GCPItem(
                        id=parts[id_idx],
                        x=float(parts[x_idx]),
                        y=float(parts[y_idx]),
                        elevation=float(parts[elev_idx])
                    ))
                except ValueError:
                    continue
        return gcps
