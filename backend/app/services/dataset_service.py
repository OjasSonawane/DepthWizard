import os
import json
import uuid
import shutil
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from PIL import Image

from app.config import settings
from app.services.geospatial_service import GeospatialService
from app.services.image_validator import ImageValidator
from app.schemas.schemas import DatasetSummary, ImageMetadata, DEMMetadata, GCPItem, InputValidationResult

logger = logging.getLogger("depthwizard.dataset")

class DatasetService:
    _instance: Optional["DatasetService"] = None

    def __init__(self):
        self.datasets: Dict[str, DatasetSummary] = {}
        self.active_dataset_id: Optional[str] = None
        self.cache_dir = settings.DATASETS_DIR / "preloaded_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @classmethod
    def get_instance(cls) -> "DatasetService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def initialize(self):
        """
        Scans both preloaded demonstration datasets and persisted user uploads.
        """
        self.datasets.clear()
        self._scan_preloaded_datasets()
        self._scan_user_datasets()
        # Default active dataset to himalayan_valley if available, or first dataset
        if not self.active_dataset_id or self.active_dataset_id not in self.datasets:
            if "himalayan_valley" in self.datasets:
                self.active_dataset_id = "himalayan_valley"
            elif self.datasets:
                self.active_dataset_id = next(iter(self.datasets.keys()))

    def _scan_preloaded_datasets(self):
        """
        Registers authentic preloaded datasets from settings.SAMPLES_DIR.
        """
        if not settings.SAMPLES_DIR.exists():
            return

        for sample_dir in sorted(settings.SAMPLES_DIR.iterdir()):
            if not sample_dir.is_dir():
                continue
            meta_path = sample_dir / "metadata.json"
            if not meta_path.exists():
                continue

            try:
                with open(meta_path, "r") as f:
                    raw_meta = json.load(f)

                sample_id = sample_dir.name
                img_name = raw_meta.get("imagery_file")
                if not img_name:
                    continue
                img_path = sample_dir / img_name
                if not img_path.exists():
                    continue

                # Inspect image
                meta, rgb_array = GeospatialService.inspect_file(img_path)

                # Generate cached thumbnail & preview if missing
                sample_cache = self.cache_dir / sample_id
                sample_cache.mkdir(parents=True, exist_ok=True)
                thumb_path = sample_cache / "thumbnail.jpg"
                prev_path = sample_cache / "preview.jpg"

                if not thumb_path.exists() or not prev_path.exists():
                    pil_img = Image.fromarray(rgb_array)
                    # Thumbnail (256x256 max)
                    t_img = pil_img.copy()
                    t_img.thumbnail((256, 256))
                    t_img.save(thumb_path, format="JPEG", quality=85)
                    # Preview (1024x1024 max)
                    p_img = pil_img.copy()
                    p_img.thumbnail((1024, 1024))
                    p_img.save(prev_path, format="JPEG", quality=88)

                has_dem = bool(raw_meta.get("reference_dem"))
                dem_metadata_obj = None
                dem_file = raw_meta.get("reference_dem", {}).get("file") if isinstance(raw_meta.get("reference_dem"), dict) else None
                if dem_file and (sample_dir / dem_file).exists():
                    has_dem = True
                    try:
                        dem_metadata_obj = GeospatialService.inspect_dem_file(
                            dem_path=sample_dir / dem_file,
                            image_crs=meta.crs,
                            image_bounds=meta.bounds
                        )
                    except Exception:
                        pass

                has_gcps = bool(raw_meta.get("ground_control_points"))
                gcp_items = None
                gcp_file = raw_meta.get("ground_control_points", {}).get("file") if isinstance(raw_meta.get("ground_control_points"), dict) else None
                if gcp_file and (sample_dir / gcp_file).exists():
                    has_gcps = True
                    from app.services.depth_service import PipelineManager
                    try:
                        gcp_items = PipelineManager.get_instance()._parse_gcp_csv(sample_dir / gcp_file)
                    except Exception:
                        pass

                # Run input validation for preloaded imagery
                val_res = None
                try:
                    val_res = ImageValidator.validate_image(img_path)
                except Exception as ve:
                    logger.debug(f"Preloaded validation fallback for {sample_id}: {ve}")

                summary = DatasetSummary(
                    id=sample_id,
                    name=raw_meta.get("title", sample_id.replace("_", " ").title()),
                    source="preloaded",
                    original_filename=img_name,
                    file_type=img_path.suffix.lstrip(".").lower(),
                    width=meta.width,
                    height=meta.height,
                    channels=meta.band_count,
                    georeferenced=meta.is_georeferenced,
                    crs=meta.crs,
                    transform=meta.transform,
                    bounds=meta.bounds,
                    resolution=meta.resolution,
                    nodata=meta.nodata,
                    dtype=meta.datatype,
                    classification=meta.classification,
                    is_low_resolution=meta.is_low_resolution,
                    resolution_warning=meta.resolution_warning,
                    has_dem=has_dem,
                    dem_metadata=dem_metadata_obj,
                    has_gcps=has_gcps,
                    parsed_gcps=gcp_items,
                    created_at="2026-09-08T00:00:00Z",
                    status="ready",
                    preview_url=f"/api/datasets/{sample_id}/preview",
                    thumbnail_url=f"/api/datasets/{sample_id}/thumbnail",
                    active_job_id=None,
                    latest_results=None,
                    input_validation=val_res
                )
                self.datasets[sample_id] = summary
                logger.info(f"Loaded preloaded dataset: {sample_id} ({summary.width}x{summary.height})")
            except Exception as e:
                logger.error(f"Failed to load preloaded dataset {sample_dir.name}: {e}", exc_info=True)

    def _scan_user_datasets(self):
        """
        Scans persistent storage/datasets for user-uploaded datasets.
        """
        if not settings.DATASETS_DIR.exists():
            return

        for ds_dir in sorted(settings.DATASETS_DIR.iterdir()):
            if not ds_dir.is_dir() or ds_dir.name == "preloaded_cache":
                continue
            meta_path = ds_dir / "metadata.json"
            if not meta_path.exists():
                continue

            try:
                with open(meta_path, "r") as f:
                    data = json.load(f)

                ds_id = ds_dir.name
                # Check for image file
                orig_file = data.get("original_filename")
                img_path = None
                for candidate in ds_dir.glob("original.*"):
                    img_path = candidate
                    break

                if not img_path or not img_path.exists():
                    continue

                # Ensure thumbnail and preview exist
                thumb_path = ds_dir / "thumbnail.jpg"
                prev_path = ds_dir / "preview.jpg"
                if not thumb_path.exists() or not prev_path.exists():
                    meta, rgb_array = GeospatialService.inspect_file(img_path)
                    pil_img = Image.fromarray(rgb_array)
                    t_img = pil_img.copy()
                    t_img.thumbnail((256, 256))
                    t_img.save(thumb_path, format="JPEG", quality=85)
                    p_img = pil_img.copy()
                    p_img.thumbnail((1024, 1024))
                    p_img.save(prev_path, format="JPEG", quality=88)

                # Check if job exists in PipelineManager
                from app.services.depth_service import PipelineManager
                pipeline = PipelineManager.get_instance()
                active_job_id = data.get("active_job_id")
                latest_results = None
                status = data.get("status", "ready")
                if active_job_id and active_job_id in pipeline.jobs:
                    job = pipeline.jobs[active_job_id]
                    if job.get("status") == "completed" and job.get("results"):
                        status = "completed"
                        from app.schemas.schemas import ReconstructionSummary
                        latest_results = ReconstructionSummary(**job["results"])

                # Load or compute input validation
                val_file = ds_dir / "input_validation.json"
                val_res = None
                if val_file.exists():
                    try:
                        with open(val_file, "r") as f:
                            val_res = InputValidationResult(**json.load(f))
                    except Exception:
                        pass
                if val_res is None:
                    try:
                        val_res = ImageValidator.validate_image(img_path)
                        with open(val_file, "w") as f:
                            json.dump(val_res.model_dump(), f, indent=2)
                    except Exception as ve:
                        logger.debug(f"User dataset validation fallback for {ds_id}: {ve}")

                if val_res and val_res.status == "rejected" and status != "completed":
                    status = "rejected"

                dem_meta_obj = DEMMetadata(**data["dem_metadata"]) if data.get("dem_metadata") else None
                gcp_items = [GCPItem(**g) for g in data["parsed_gcps"]] if data.get("parsed_gcps") else None

                summary = DatasetSummary(
                    id=ds_id,
                    name=data.get("name", orig_file),
                    source="user_upload",
                    original_filename=orig_file,
                    file_type=data.get("file_type", img_path.suffix.lstrip(".").lower()),
                    width=data["width"],
                    height=data["height"],
                    channels=data.get("channels", 3),
                    georeferenced=data["georeferenced"],
                    crs=data.get("crs"),
                    transform=data.get("transform"),
                    bounds=data.get("bounds"),
                    resolution=data.get("resolution"),
                    nodata=data.get("nodata"),
                    dtype=data.get("dtype", "uint8"),
                    classification=data.get("classification"),
                    is_low_resolution=data.get("is_low_resolution", False),
                    resolution_warning=data.get("resolution_warning"),
                    has_dem=data.get("has_dem", False),
                    dem_metadata=dem_meta_obj,
                    has_gcps=data.get("has_gcps", False),
                    parsed_gcps=gcp_items,
                    created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
                    status=status,
                    preview_url=f"/api/datasets/{ds_id}/preview",
                    thumbnail_url=f"/api/datasets/{ds_id}/thumbnail",
                    active_job_id=active_job_id,
                    latest_results=latest_results,
                    input_validation=val_res
                )
                self.datasets[ds_id] = summary
                logger.info(f"Loaded persistent user dataset: {ds_id} ({summary.name})")
            except Exception as e:
                logger.error(f"Failed to load user dataset {ds_dir.name}: {e}", exc_info=True)

    def create_user_dataset(
        self,
        image_bytes: bytes,
        original_filename: str,
        dem_bytes: Optional[bytes] = None,
        dem_filename: Optional[str] = None,
        gcp_bytes: Optional[bytes] = None,
        gcp_filename: Optional[str] = None
    ) -> DatasetSummary:
        """
        Persistently saves user-uploaded imagery, generates thumbnails, extracts metadata.
        """
        ext = Path(original_filename).suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported image format '{ext}'. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}")

        dataset_id = f"dw_ds_{uuid.uuid4().hex[:8]}"
        ds_dir = settings.DATASETS_DIR / dataset_id
        ds_dir.mkdir(parents=True, exist_ok=True)

        # 1. Save original image
        img_save_path = ds_dir / f"original{ext}"
        with open(img_save_path, "wb") as f:
            f.write(image_bytes)

        # 2. Extract metadata and normalized RGB
        meta, rgb_array = GeospatialService.inspect_file(img_save_path)

        # 3. Generate thumbnail (256x256) and preview (1024x1024)
        pil_img = Image.fromarray(rgb_array)
        thumb_path = ds_dir / "thumbnail.jpg"
        t_img = pil_img.copy()
        t_img.thumbnail((256, 256))
        t_img.save(thumb_path, format="JPEG", quality=85)

        prev_path = ds_dir / "preview.jpg"
        p_img = pil_img.copy()
        p_img.thumbnail((1024, 1024))
        p_img.save(prev_path, format="JPEG", quality=88)

        # 4. Handle optional DEM
        dem_save_path = None
        dem_metadata_obj = None
        if dem_bytes and dem_filename:
            d_ext = Path(dem_filename).suffix.lower()
            if d_ext in [".tif", ".tiff"]:
                dem_save_path = ds_dir / f"dem{d_ext}"
                with open(dem_save_path, "wb") as f:
                    f.write(dem_bytes)
                dem_metadata_obj = GeospatialService.inspect_dem_file(
                    dem_path=dem_save_path,
                    image_crs=meta.crs,
                    image_bounds=meta.bounds
                )

        # 5. Handle optional GCPs
        gcp_save_path = None
        gcp_items = None
        if gcp_bytes and gcp_filename:
            g_ext = Path(gcp_filename).suffix.lower()
            if g_ext in [".csv", ".txt"]:
                gcp_save_path = ds_dir / f"gcps{g_ext}"
                with open(gcp_save_path, "wb") as f:
                    f.write(gcp_bytes)
                from app.services.depth_service import PipelineManager
                try:
                    gcp_items = PipelineManager.get_instance()._parse_gcp_csv(gcp_save_path)
                except Exception:
                    pass

        # 6. Content Validation
        val_res = ImageValidator.validate_image(img_save_path)
        with open(ds_dir / "input_validation.json", "w") as f:
            json.dump(val_res.model_dump(), f, indent=2)

        initial_status = "rejected" if val_res.status == "rejected" else "ready"

        now_str = datetime.now(timezone.utc).isoformat()
        dataset_meta_dict = {
            "id": dataset_id,
            "name": original_filename,
            "source": "user_upload",
            "original_filename": original_filename,
            "file_type": ext.lstrip("."),
            "width": meta.width,
            "height": meta.height,
            "channels": meta.band_count,
            "georeferenced": meta.is_georeferenced,
            "crs": meta.crs,
            "transform": meta.transform,
            "bounds": meta.bounds,
            "resolution": meta.resolution,
            "nodata": meta.nodata,
            "dtype": meta.datatype,
            "classification": meta.classification,
            "is_low_resolution": meta.is_low_resolution,
            "resolution_warning": meta.resolution_warning,
            "has_dem": dem_save_path is not None,
            "dem_metadata": dem_metadata_obj.model_dump() if dem_metadata_obj else None,
            "has_gcps": gcp_save_path is not None,
            "parsed_gcps": [g.model_dump() for g in gcp_items] if gcp_items else None,
            "created_at": now_str,
            "status": initial_status,
            "active_job_id": None,
            "input_validation": val_res.model_dump()
        }

        # Save metadata.json
        with open(ds_dir / "metadata.json", "w") as f:
            json.dump(dataset_meta_dict, f, indent=2)

        summary = DatasetSummary(
            id=dataset_id,
            name=original_filename,
            source="user_upload",
            original_filename=original_filename,
            file_type=ext.lstrip("."),
            width=meta.width,
            height=meta.height,
            channels=meta.band_count,
            georeferenced=meta.is_georeferenced,
            crs=meta.crs,
            transform=meta.transform,
            bounds=meta.bounds,
            resolution=meta.resolution,
            nodata=meta.nodata,
            dtype=meta.datatype,
            classification=meta.classification,
            is_low_resolution=meta.is_low_resolution,
            resolution_warning=meta.resolution_warning,
            has_dem=dem_save_path is not None,
            dem_metadata=dem_metadata_obj,
            has_gcps=gcp_save_path is not None,
            parsed_gcps=gcp_items,
            created_at=now_str,
            status=initial_status,
            preview_url=f"/api/datasets/{dataset_id}/preview",
            thumbnail_url=f"/api/datasets/{dataset_id}/thumbnail",
            active_job_id=None,
            latest_results=None,
            input_validation=val_res
        )

        self.datasets[dataset_id] = summary
        self.active_dataset_id = dataset_id
        logger.info(f"Successfully created, validated ({val_res.status}), and persisted dataset {dataset_id} ({original_filename})")
        return summary

    def get_dataset(self, dataset_id: str) -> DatasetSummary:
        if dataset_id not in self.datasets:
            raise KeyError(f"Dataset '{dataset_id}' not found.")
        return self.datasets[dataset_id]

    def get_all_datasets(self) -> List[DatasetSummary]:
        """
        Returns user uploads followed by preloaded datasets.
        """
        user_ds = [d for d in self.datasets.values() if d.source == "user_upload"]
        preloaded_ds = [d for d in self.datasets.values() if d.source == "preloaded"]
        return user_ds + preloaded_ds

    def delete_dataset(self, dataset_id: str) -> bool:
        """
        Deletes a user-uploaded dataset from disk and registry.
        """
        if dataset_id not in self.datasets:
            raise KeyError(f"Dataset '{dataset_id}' not found.")
        ds = self.datasets[dataset_id]
        if ds.source == "preloaded":
            raise ValueError("Preloaded demonstration datasets cannot be deleted.")

        ds_dir = settings.DATASETS_DIR / dataset_id
        if ds_dir.exists():
            shutil.rmtree(ds_dir, ignore_errors=True)

        del self.datasets[dataset_id]
        if self.active_dataset_id == dataset_id:
            # Fallback to another dataset
            if "himalayan_valley" in self.datasets:
                self.active_dataset_id = "himalayan_valley"
            elif self.datasets:
                self.active_dataset_id = next(iter(self.datasets.keys()))
            else:
                self.active_dataset_id = None
        logger.info(f"Deleted dataset {dataset_id}")
        return True

    def select_dataset(self, dataset_id: str) -> DatasetSummary:
        if dataset_id not in self.datasets:
            raise KeyError(f"Dataset '{dataset_id}' not found.")
        self.active_dataset_id = dataset_id
        return self.datasets[dataset_id]

    def get_thumbnail_path(self, dataset_id: str) -> Path:
        if dataset_id not in self.datasets:
            raise KeyError(f"Dataset '{dataset_id}' not found.")
        ds = self.datasets[dataset_id]
        if ds.source == "preloaded":
            p = self.cache_dir / dataset_id / "thumbnail.jpg"
            if p.exists():
                return p
        else:
            p = settings.DATASETS_DIR / dataset_id / "thumbnail.jpg"
            if p.exists():
                return p
        raise FileNotFoundError(f"Thumbnail for dataset {dataset_id} not found.")

    def get_preview_path(self, dataset_id: str) -> Path:
        if dataset_id not in self.datasets:
            raise KeyError(f"Dataset '{dataset_id}' not found.")
        ds = self.datasets[dataset_id]
        if ds.source == "preloaded":
            p = self.cache_dir / dataset_id / "preview.jpg"
            if p.exists():
                return p
        else:
            p = settings.DATASETS_DIR / dataset_id / "preview.jpg"
            if p.exists():
                return p
        raise FileNotFoundError(f"Preview for dataset {dataset_id} not found.")

    def get_dataset_files(self, dataset_id: str) -> Dict[str, Any]:
        """
        Returns paths to the actual image, DEM, and GCP files for the dataset.
        """
        if dataset_id not in self.datasets:
            raise KeyError(f"Dataset '{dataset_id}' not found.")
        ds = self.datasets[dataset_id]

        if ds.source == "preloaded":
            sample_dir = settings.SAMPLES_DIR / dataset_id
            with open(sample_dir / "metadata.json") as f:
                meta = json.load(f)
            img_path = sample_dir / meta["imagery_file"]
            dem_path = None
            if meta.get("reference_dem"):
                dem_file = meta["reference_dem"].get("file") if isinstance(meta["reference_dem"], dict) else None
                if dem_file and (sample_dir / dem_file).exists():
                    dem_path = sample_dir / dem_file
            gcp_path = None
            if meta.get("ground_control_points"):
                gcp_file = meta["ground_control_points"].get("file") if isinstance(meta["ground_control_points"], dict) else None
                if gcp_file and (sample_dir / gcp_file).exists():
                    gcp_path = sample_dir / gcp_file
            return {
                "image_path": img_path,
                "dem_path": dem_path,
                "gcp_path": gcp_path
            }
        else:
            ds_dir = settings.DATASETS_DIR / dataset_id
            img_path = None
            for c in ds_dir.glob("original.*"):
                img_path = c
                break
            dem_path = None
            for c in ds_dir.glob("dem.*"):
                dem_path = c
                break
            gcp_path = None
            for c in ds_dir.glob("gcps*.*"):
                gcp_path = c
                break
            return {
                "image_path": img_path,
                "dem_path": dem_path,
                "gcp_path": gcp_path
            }

    def prepare_job(self, dataset_id: str) -> str:
        """
        Prepares a job in PipelineManager for this dataset and returns the generated job_id.
        """
        from app.services.depth_service import PipelineManager
        ds = self.get_dataset(dataset_id)
        if ds.input_validation and ds.input_validation.status == "rejected":
            raise ValueError(f"Dataset reconstruction blocked: {ds.input_validation.rejection_reason or 'Image content rejected by quality control'}.")

        files = self.get_dataset_files(dataset_id)
        if not files["image_path"] or not Path(files["image_path"]).exists():
            raise FileNotFoundError(f"Image file for dataset '{dataset_id}' not found.")

        job_id = f"dw_job_{uuid.uuid4().hex[:8]}"
        meta, _ = GeospatialService.inspect_file(Path(files["image_path"]))

        dem_metadata = None
        if files["dem_path"] and Path(files["dem_path"]).exists():
            dem_metadata = GeospatialService.inspect_dem_file(
                dem_path=Path(files["dem_path"]),
                image_crs=meta.crs,
                image_bounds=meta.bounds
            )

        pipeline = PipelineManager.get_instance()
        pipeline.register_job(
            job_id=job_id,
            image_path=str(files["image_path"]),
            metadata=meta,
            dem_path=str(files["dem_path"]) if files["dem_path"] else None,
            gcp_path=str(files["gcp_path"]) if files["gcp_path"] else None,
            dem_metadata=dem_metadata,
            dataset_id=dataset_id
        )

        ds.active_job_id = job_id
        return job_id

    def update_dataset_job(self, dataset_id: str, job_id: str, results: Any = None):
        """
        Links an executed reconstruction job to the dataset.
        """
        if dataset_id in self.datasets:
            ds = self.datasets[dataset_id]
            ds.active_job_id = job_id
            ds.status = "completed" if results else "processing"
            ds.latest_results = results

            # Persist to metadata.json if user upload
            if ds.source == "user_upload":
                meta_path = settings.DATASETS_DIR / dataset_id / "metadata.json"
                if meta_path.exists():
                    try:
                        with open(meta_path, "r") as f:
                            data = json.load(f)
                        data["active_job_id"] = job_id
                        data["status"] = ds.status
                        with open(meta_path, "w") as f:
                            json.dump(data, f, indent=2)
                    except Exception as e:
                        logger.warning(f"Could not update metadata for dataset {dataset_id}: {e}")
