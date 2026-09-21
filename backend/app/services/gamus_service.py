import io
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import h5py
import numpy as np
from PIL import Image
from scipy.stats import pearsonr, spearmanr
from sklearn.linear_model import HuberRegressor, LinearRegression
from sklearn.metrics import r2_score
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure

from app.config import settings
from app.models.depth_model import DepthEstimator
from app.schemas.gamus_schemas import (
    CalibrationInfo,
    CalibrationMode,
    GAMUSCatalogItem,
    GAMUSEvaluationMetrics,
    GAMUSEvaluationRequest,
    GAMUSEvaluationResult,
    GAMUSExperimentRecord,
    GAMUSSampleRecord,
    GAMUSScatterPoint,
    GAMUSSplit,
    ReferenceHeightMetadata,
    RGBMetadata,
)

logger = logging.getLogger("depthwizard.gamus")


class GAMUSError(Exception):
    """Base exception for GAMUS benchmark operations."""
    pass


class SampleNotFoundError(GAMUSError):
    """Raised when a requested sample cannot be located in local cache or remote repo."""
    pass


class SpatialMismatchError(GAMUSError):
    """Raised when RGB imagery and reference height rasters have incompatible dimensions."""
    pass


class SemanticViolationError(GAMUSError):
    """Raised when height semantics or elevation units are violated."""
    pass


class TestSetCalibrationProhibitedError(GAMUSError):
    """
    Raised when an attempt is made to calibrate against a test set sample.
    To preserve scientific integrity and prevent data leakage, calibration directly
    on the test set is strictly prohibited.
    """
    __test__ = False


class SplitNotSupportedError(GAMUSError):
    """Raised when an unrecognized dataset split is requested."""
    pass


class GAMUSService:
    """
    Comprehensive scientific benchmark integration service for the GAMUS dataset
    (arXiv:2305.14914).
    
    Supports:
    - Lazy streaming sample access via huggingface_hub without downloading the full ~100GB repository.
    - Exact RGB-to-height pairing verification.
    - Strict sample ID and split preservation.
    - Height semantics enforcement (AGL / nDSM in meters; non-absolute elevation).
    - Depth Anything V2 inference.
    - Anti-data leakage test set calibration prohibition.
    - Train-to-test calibration transfer.
    - Computation of MAE, RMSE, Pearson r, Spearman rho, R2, MBE, LE90, LE95.
    - Signed and absolute error map generation.
    - Subsampled scatter plot generation with regression & identity diagnostics.
    - Full experiment metadata tracking and persistent JSON storage.
    """
    
    REPO_ID = "earthflow/GAMUS"
    KNOWN_SPLITS = {"train", "val", "test"}
    
    # Pre-indexed representative sample catalog for instant offline lookups
    REPRESENTATIVE_SAMPLES = {
        "test": ["NYC_00735", "NYC_00918", "NYC_00984", "NYC_01289", "NYC_01302"],
        "train": ["NYC_22835", "NYC_22836", "NYC_22837", "NYC_22838", "NYC_22839"],
        "val": ["NYC_18001", "NYC_18002", "NYC_18003"]
    }

    def __init__(self):
        self.storage_base = settings.STORAGE_DIR / "benchmarks" / "gamus"
        self.cache_dir = self.storage_base / "cache"
        self.fixtures_dir = self.storage_base / "fixtures"
        self.experiments_dir = settings.STORAGE_DIR / "experiments" / "gamus"
        
        for d in [self.storage_base, self.cache_dir, self.fixtures_dir, self.experiments_dir]:
            d.mkdir(parents=True, exist_ok=True)
            
        self._catalog_cache: Optional[Dict[str, List[str]]] = None

    def _get_hf_cache_dir(self) -> Path:
        return Path.home() / ".cache" / "huggingface" / "hub"

    def list_catalog(self, split: Optional[str] = None) -> List[GAMUSCatalogItem]:
        """
        List available sample IDs by split without downloading the full dataset.
        Combines locally cached files, fixtures, and known representative samples.
        """
        if split and split not in self.KNOWN_SPLITS:
            raise SplitNotSupportedError(f"Split '{split}' is invalid. Must be one of {self.KNOWN_SPLITS}.")

        target_splits = [split] if split else sorted(list(self.KNOWN_SPLITS))
        catalog_items: List[GAMUSCatalogItem] = []
        seen = set()

        for s in target_splits:
            # 1. Check local fixtures
            split_fixture_dir = self.fixtures_dir / s
            if split_fixture_dir.exists():
                for img_path in split_fixture_dir.glob("*_IMG.h5"):
                    sid = img_path.name.replace("_IMG.h5", "")
                    agl_path = split_fixture_dir / f"{sid}_AGL.h5"
                    if agl_path.exists() and (s, sid) not in seen:
                        seen.add((s, sid))
                        catalog_items.append(
                            GAMUSCatalogItem(
                                sample_id=sid,
                                split=s,
                                img_file=img_path.name,
                                agl_file=agl_path.name,
                                is_cached=True
                            )
                        )

            # 2. Check local storage cache
            split_cache_dir = self.cache_dir / s
            if split_cache_dir.exists():
                for img_path in split_cache_dir.glob("*_IMG.h5"):
                    sid = img_path.name.replace("_IMG.h5", "")
                    agl_path = split_cache_dir / f"{sid}_AGL.h5"
                    if agl_path.exists() and (s, sid) not in seen:
                        seen.add((s, sid))
                        catalog_items.append(
                            GAMUSCatalogItem(
                                sample_id=sid,
                                split=s,
                                img_file=img_path.name,
                                agl_file=agl_path.name,
                                is_cached=True
                            )
                        )

            # 3. Check HuggingFace hub cache
            hf_cache = self._get_hf_cache_dir()
            if hf_cache.exists():
                for img_path in hf_cache.glob(f"**/{s}/*_IMG.h5"):
                    sid = img_path.name.replace("_IMG.h5", "")
                    agl_path = img_path.parent.parent.parent / "heights" / s / f"{sid}_AGL.h5"
                    # Also look in same directory structure or sibling snapshots
                    if (s, sid) not in seen:
                        seen.add((s, sid))
                        catalog_items.append(
                            GAMUSCatalogItem(
                                sample_id=sid,
                                split=s,
                                img_file=img_path.name,
                                agl_file=f"{sid}_AGL.h5",
                                is_cached=True
                            )
                        )

            # 4. Include representative catalog samples (available via lazy streaming)
            for sid in self.REPRESENTATIVE_SAMPLES.get(s, []):
                if (s, sid) not in seen:
                    seen.add((s, sid))
                    catalog_items.append(
                        GAMUSCatalogItem(
                            sample_id=sid,
                            split=s,
                            img_file=f"{sid}_IMG.h5",
                            agl_file=f"{sid}_AGL.h5",
                            is_cached=False
                        )
                    )

        return catalog_items

    def fetch_sample_files(self, split: str, sample_id: str) -> Tuple[Path, Path]:
        """
        Lazy streaming access: locate or on-demand stream only the specific
        RGB image (.h5) and reference height (.h5) files for the given sample ID.
        Never downloads the full dataset.
        """
        if split not in self.KNOWN_SPLITS:
            raise SplitNotSupportedError(f"Split '{split}' is invalid. Must be one of {self.KNOWN_SPLITS}.")

        img_filename = f"{sample_id}_IMG.h5"
        agl_filename = f"{sample_id}_AGL.h5"

        # 1. Check local fixture directory
        fixture_img = self.fixtures_dir / split / img_filename
        fixture_agl = self.fixtures_dir / split / agl_filename
        if fixture_img.exists() and fixture_agl.exists():
            return fixture_img, fixture_agl

        # 2. Check local storage cache directory
        cache_img = self.cache_dir / split / img_filename
        cache_agl = self.cache_dir / split / agl_filename
        if cache_img.exists() and cache_agl.exists():
            return cache_img, cache_agl

        # 3. Check HuggingFace hub cache
        hf_cache = self._get_hf_cache_dir()
        if hf_cache.exists():
            matching_imgs = list(hf_cache.glob(f"**/{split}/{img_filename}"))
            matching_agls = list(hf_cache.glob(f"**/{split}/{agl_filename}"))
            if matching_imgs and matching_agls:
                return matching_imgs[0], matching_agls[0]

        # 4. Lazy streaming download of ONLY this single sample pair via huggingface_hub
        try:
            from huggingface_hub import hf_hub_download
            logger.info(f"Lazy streaming sample {sample_id} ({split}) from {self.REPO_ID}...")
            
            # Download RGB image
            dl_img = hf_hub_download(
                repo_id=self.REPO_ID,
                repo_type="dataset",
                filename=f"images/{split}/{img_filename}"
            )
            # Download Height raster
            dl_agl = hf_hub_download(
                repo_id=self.REPO_ID,
                repo_type="dataset",
                filename=f"heights/{split}/{agl_filename}"
            )
            return Path(dl_img), Path(dl_agl)
        except Exception as e:
            raise SampleNotFoundError(
                f"Sample '{sample_id}' in split '{split}' could not be streamed or found. Details: {e}"
            )

    def load_sample_arrays(self, split: str, sample_id: str) -> Tuple[np.ndarray, np.ndarray, GAMUSSampleRecord]:
        """
        Load RGB image and reference height arrays, verify exact pairing,
        validate height semantics, and generate a certified sample record.
        """
        img_path, agl_path = self.fetch_sample_files(split, sample_id)

        # Verify filename pairing
        if not img_path.name.startswith(sample_id) or not agl_path.name.startswith(sample_id):
            raise SpatialMismatchError(
                f"File pairing mismatch: {img_path.name} does not match {agl_path.name} for sample ID '{sample_id}'."
            )

        with h5py.File(img_path, "r") as f_img:
            if "image" not in f_img:
                raise KeyError(f"Dataset key 'image' missing in {img_path}")
            rgb = f_img["image"][:]

        with h5py.File(agl_path, "r") as f_agl:
            if "image" not in f_agl:
                raise KeyError(f"Dataset key 'image' missing in {agl_path}")
            height = f_agl["image"][:]

        # Verify RGB dimensions: (H, W, 3)
        if rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError(f"RGB array must have shape (H, W, 3), found {rgb.shape}")

        # Verify Height dimensions: (H, W)
        if height.ndim != 2:
            raise ValueError(f"Reference height array must be 2D (H, W), found {height.shape}")

        # Verify spatial co-registration / shape match
        if rgb.shape[:2] != height.shape:
            raise SpatialMismatchError(
                f"Exact spatial mismatch between RGB image {rgb.shape[:2]} and reference height {height.shape}."
            )

        # Extract height statistics
        valid_mask = np.isfinite(height)
        valid_count = int(np.count_nonzero(valid_mask))
        if valid_count == 0:
            raise ValueError("Reference height contains zero valid finite pixels.")

        h_valid = height[valid_mask]
        min_val = float(np.min(h_valid))
        max_val = float(np.max(h_valid))
        mean_val = float(np.mean(h_valid))
        std_val = float(np.std(h_valid))
        valid_pct = float((valid_count / height.size) * 100.0)

        # Build certified sample record
        sample_record = GAMUSSampleRecord(
            sample_id=sample_id,
            split=split,
            rgb_metadata=RGBMetadata(
                shape=list(rgb.shape),
                dtype=str(rgb.dtype),
                channels=3,
                min_val=int(np.min(rgb)),
                max_val=int(np.max(rgb)),
                channel_order="RGB"
            ),
            reference_metadata=ReferenceHeightMetadata(
                field_name="AGL",
                type="nDSM (Height Above Ground Level)",
                is_absolute_elevation=False,
                vertical_datum="Ground Level (AGL = 0.0m)",
                units="meters",
                shape=list(height.shape),
                dtype=str(height.dtype),
                min_val=min_val,
                max_val=max_val,
                mean_val=mean_val,
                std_val=std_val,
                valid_pixel_pct=round(valid_pct, 2),
                disclaimer="Reference height represents Above Ground Level (AGL / nDSM) in meters, NOT absolute elevation (AMSL)."
            ),
            created_at=datetime.now(timezone.utc).isoformat()
        )

        return rgb, height, sample_record

    def evaluate_sample(self, req: GAMUSEvaluationRequest) -> GAMUSEvaluationResult:
        """
        Execute full benchmark evaluation on a GAMUS sample:
        1. Load RGB and AGL reference height.
        2. Run Depth Anything V2 inference.
        3. Enforce anti-leakage rules: strictly prohibit calibrating on the test set.
        4. Apply zero-shot relative comparison or train-to-test calibration transfer.
        5. Calculate MAE, RMSE, Pearson r, Spearman rho, R2, MBE, LE90, LE95.
        6. Generate signed and absolute error maps.
        7. Generate publication-quality predicted-vs-reference scatter plot.
        8. Record complete experiment metadata and persist to disk.
        """
        t_start = time.time()
        timings: Dict[str, float] = {}

        # 1. Anti-leakage guardrail
        if req.split == "test" and req.calibration_mode == CalibrationMode.DIRECT_FIT_TRAIN_VAL:
            raise TestSetCalibrationProhibitedError(
                "Calibrating directly on the test set is strictly prohibited to prevent data leakage. "
                "Use 'zero_shot_relative' for scale-invariant evaluation or 'train_calibrated_transfer' "
                "to apply calibration parameters fitted strictly on the train split."
            )

        # 2. Ingest and validate sample pairing & semantics
        t0 = time.time()
        rgb, ref_agl, sample_record = self.load_sample_arrays(req.split, req.sample_id)
        timings["data_loading"] = round(time.time() - t0, 3)

        # 3. Depth Anything V2 Inference
        t0 = time.time()
        estimator = DepthEstimator.get_instance()
        pred_relative = estimator.predict(rgb)
        timings["inference"] = round(time.time() - t0, 3)

        # 4. Calibration handling with anti-data leakage enforcement
        t0 = time.time()
        calib_info: CalibrationInfo
        pred_for_eval: np.ndarray
        ref_for_eval: np.ndarray

        if req.split == "test":
            if req.calibration_mode == CalibrationMode.TRAIN_CALIBRATED_TRANSFER:
                # Calibration transfer: fit on train sample, apply to test
                train_sid = req.train_calibration_sample_id or "NYC_22835"
                logger.info(f"Deriving calibration parameters strictly from train sample '{train_sid}'...")
                
                rgb_train, agl_train, _ = self.load_sample_arrays("train", train_sid)
                pred_train = estimator.predict(rgb_train)
                
                # Fit Huber regression on valid train pixels
                train_mask = np.isfinite(pred_train) & np.isfinite(agl_train)
                x_tr = pred_train[train_mask].reshape(-1, 1)
                y_tr = agl_train[train_mask]
                
                if len(y_tr) > 30000:
                    rng = np.random.RandomState(42)
                    tr_idx = rng.choice(len(y_tr), 30000, replace=False)
                    x_tr = x_tr[tr_idx]
                    y_tr = y_tr[tr_idx]

                try:
                    reg = HuberRegressor(epsilon=1.35, max_iter=300)
                    reg.fit(x_tr, y_tr)
                    scale = float(reg.coef_[0])
                    offset = float(reg.intercept_)
                except Exception:
                    reg = LinearRegression()
                    reg.fit(x_tr, y_tr)
                    scale = float(reg.coef_[0])
                    offset = float(reg.intercept_)

                if scale < 0.0:
                    # Invert polarity based on train relationship
                    x_tr = 1.0 - x_tr
                    reg.fit(x_tr, y_tr)
                    scale = float(reg.coef_[0])
                    offset = float(reg.intercept_)
                    pred_test_adj = 1.0 - pred_relative
                else:
                    pred_test_adj = pred_relative

                pred_for_eval = (pred_test_adj * scale + offset).astype(np.float32)
                ref_for_eval = ref_agl

                calib_info = CalibrationInfo(
                    mode=CalibrationMode.TRAIN_CALIBRATED_TRANSFER.value,
                    source_split="train",
                    source_sample_id=train_sid,
                    scale=round(scale, 4),
                    offset=round(offset, 4),
                    applied_to_test=True,
                    message=(
                        f"Calibration scale ({scale:.4f}) and offset ({offset:.4f}) fitted strictly on "
                        f"train sample '{train_sid}' and transferred to test sample without test leakage."
                    )
                )

            else:
                # Zero-shot relative evaluation: scale-invariant metrics
                calib_info = CalibrationInfo(
                    mode=CalibrationMode.ZERO_SHOT_RELATIVE.value,
                    source_split=None,
                    source_sample_id=None,
                    scale=None,
                    offset=None,
                    applied_to_test=False,
                    message="Zero-shot evaluation: evaluated directly as relative depth geometry without test-set calibration."
                )
                pred_for_eval = pred_relative
                # Normalize reference AGL to [0, 1] relative range for normalized MAE/RMSE comparisons
                ref_min = np.nanmin(ref_agl)
                ref_max = np.nanmax(ref_agl)
                ref_range = ref_max - ref_min if (ref_max - ref_min) > 1e-6 else 1.0
                ref_for_eval = ((ref_agl - ref_min) / ref_range).astype(np.float32)

        else:
            # For train / val split: direct calibration fit is permitted
            valid_tr = np.isfinite(pred_relative) & np.isfinite(ref_agl)
            x_v = pred_relative[valid_tr].reshape(-1, 1)
            y_v = ref_agl[valid_tr]
            
            rng = np.random.RandomState(42)
            if len(y_v) > 30000:
                s_idx = rng.choice(len(y_v), 30000, replace=False)
                x_v = x_v[s_idx]
                y_v = y_v[s_idx]
                
            try:
                reg = HuberRegressor(epsilon=1.35, max_iter=300)
                reg.fit(x_v, y_v)
                scale = float(reg.coef_[0])
                offset = float(reg.intercept_)
            except Exception:
                reg = LinearRegression()
                reg.fit(x_v, y_v)
                scale = float(reg.coef_[0])
                offset = float(reg.intercept_)

            if scale < 0.0:
                x_v = 1.0 - x_v
                reg.fit(x_v, y_v)
                scale = float(reg.coef_[0])
                offset = float(reg.intercept_)
                pred_adj = 1.0 - pred_relative
            else:
                pred_adj = pred_relative

            pred_for_eval = (pred_adj * scale + offset).astype(np.float32)
            ref_for_eval = ref_agl

            calib_info = CalibrationInfo(
                mode=req.calibration_mode.value,
                source_split=req.split,
                source_sample_id=req.sample_id,
                scale=round(scale, 4),
                offset=round(offset, 4),
                applied_to_test=False,
                message=f"Calibrated directly on {req.split} sample '{req.sample_id}'."
            )

        timings["calibration"] = round(time.time() - t0, 3)

        # 5. Compute Scientific Metrics
        t0 = time.time()
        valid_mask = np.isfinite(pred_for_eval) & np.isfinite(ref_for_eval)
        n_valid = int(np.count_nonzero(valid_mask))
        if n_valid < 10:
            raise ValueError(f"Insufficient valid pixels for evaluation ({n_valid} found).")

        p_vals = pred_for_eval[valid_mask].astype(np.float64)
        r_vals = ref_for_eval[valid_mask].astype(np.float64)

        # Also calculate raw relative disparity correlation with raw AGL (strictly scale-invariant)
        raw_r_vals = ref_agl[valid_mask].astype(np.float64)
        raw_p_vals = pred_relative[valid_mask].astype(np.float64)

        diff = p_vals - r_vals
        abs_diff = np.abs(diff)

        mae = float(np.mean(abs_diff))
        rmse = float(np.sqrt(np.mean(diff ** 2)))
        mbe = float(np.mean(diff))
        median_abs = float(np.median(abs_diff))
        max_abs = float(np.max(abs_diff))
        le90 = float(np.percentile(abs_diff, 90.0))
        le95 = float(np.percentile(abs_diff, 95.0))

        # Scale-invariant correlations (Pearson r and Spearman rho)
        # Using subsample for Spearman if array is large to avoid O(N log N) rank sorting latency
        rng = np.random.RandomState(42)
        corr_idx = rng.choice(len(p_vals), min(50000, len(p_vals)), replace=False) if len(p_vals) > 50000 else slice(None)
        
        pr, _ = pearsonr(raw_p_vals[corr_idx], raw_r_vals[corr_idx])
        sr, _ = spearmanr(raw_p_vals[corr_idx], raw_r_vals[corr_idx])
        
        # Polarity check: correlation could be negative if raw relative depth polarity is inverted
        pr_val = float(pr) if np.isfinite(pr) else 0.0
        sr_val = float(sr) if np.isfinite(sr) else 0.0
        
        # If calibrated, check R2
        try:
            r2 = float(r2_score(r_vals[corr_idx], p_vals[corr_idx]))
        except Exception:
            r2 = 0.0

        metrics = GAMUSEvaluationMetrics(
            mae=round(mae, 4),
            rmse=round(rmse, 4),
            pearson_r=round(abs(pr_val), 4),
            spearman_rho=round(abs(sr_val), 4),
            r2=round(r2, 4),
            mbe=round(mbe, 4),
            median_abs_error=round(median_abs, 4),
            max_abs_error=round(max_abs, 4),
            le90=round(le90, 4),
            le95=round(le95, 4),
            valid_pixels=n_valid
        )
        timings["metrics_computation"] = round(time.time() - t0, 3)

        # 6. Generate Subsampled Scatter Points
        t0 = time.time()
        scatter_size = min(req.scatter_sample_size, len(p_vals))
        sc_idx = rng.choice(len(p_vals), scatter_size, replace=False)
        p_sub = p_vals[sc_idx]
        r_sub = r_vals[sc_idx]

        scatter_points = [
            GAMUSScatterPoint(predicted=round(float(p), 4), reference=round(float(r), 4))
            for p, r in zip(p_sub, r_sub)
        ]

        # 7. Create Experiment Output Directory & Persist Artifacts
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        exp_id = f"exp_gamus_{req.split}_{req.sample_id}_{timestamp_str}"
        exp_dir = self.experiments_dir / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        # Signed error raster & colormap
        signed_error_map = np.full_like(pred_for_eval, np.nan)
        signed_error_map[valid_mask] = diff
        signed_png_path = exp_dir / "signed_error_map.png"
        self._render_signed_error_png(signed_error_map, signed_png_path, req.sample_id, req.split)

        # Absolute error raster & colormap
        abs_error_map = np.full_like(pred_for_eval, np.nan)
        abs_error_map[valid_mask] = abs_diff
        abs_png_path = exp_dir / "absolute_error_map.png"
        self._render_abs_error_png(abs_error_map, abs_png_path, req.sample_id, req.split)

        # Scatter plot PNG
        scatter_png_path = exp_dir / "scatter_plot.png"
        self._render_scatter_plot_png(
            p_sub, r_sub, metrics, scatter_png_path, req.sample_id, req.split, calib_info.mode
        )

        # Predicted depth PNG
        pred_png_path = exp_dir / "predicted_depth.png"
        pred_norm_vis = ((pred_relative - pred_relative.min()) / (pred_relative.max() - pred_relative.min() + 1e-6) * 255).astype(np.uint8)
        Image.fromarray(pred_norm_vis).save(pred_png_path)

        timings["artifact_generation"] = round(time.time() - t0, 3)
        timings["total"] = round(time.time() - t_start, 3)

        assets = {
            "signed_error_map": str(signed_png_path),
            "absolute_error_map": str(abs_png_path),
            "scatter_plot": str(scatter_png_path),
            "predicted_depth": str(pred_png_path),
            "experiment_dir": str(exp_dir)
        }

        # 8. Build Evaluation Result
        eval_result = GAMUSEvaluationResult(
            experiment_id=exp_id,
            benchmark_name="GAMUS",
            dataset_source=self.REPO_ID,
            sample_id=req.sample_id,
            split=req.split,
            model_name=settings.MODEL_NAME,
            device=settings.DEVICE.upper(),
            is_absolute_elevation=False,
            height_semantics="nDSM (Height Above Ground Level / AGL)",
            height_units="meters" if calib_info.mode != CalibrationMode.ZERO_SHOT_RELATIVE.value else "relative",
            calibration=calib_info,
            metrics=metrics,
            scatter_points=scatter_points,
            assets=assets,
            timings=timings
        )

        # 9. Build Complete Experiment Record & Persist JSON
        exp_record = GAMUSExperimentRecord(
            experiment_id=exp_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            sample_record=sample_record,
            evaluation_result=eval_result,
            environment={
                "model": settings.MODEL_NAME,
                "device": settings.DEVICE.upper(),
                "os": os.uname().sysname if hasattr(os, "uname") else "unknown",
                "huggingface_repo": self.REPO_ID
            }
        )

        record_json_path = exp_dir / "experiment_record.json"
        with open(record_json_path, "w") as f_rec:
            json.dump(exp_record.model_dump(), f_rec, indent=2)

        return eval_result

    def list_experiments(self) -> List[Dict[str, Any]]:
        """List past experiment runs from the experiments storage directory."""
        experiments = []
        if not self.experiments_dir.exists():
            return experiments

        for exp_folder in sorted(self.experiments_dir.iterdir(), reverse=True):
            if exp_folder.is_dir():
                rec_file = exp_folder / "experiment_record.json"
                if rec_file.exists():
                    try:
                        with open(rec_file, "r") as f:
                            data = json.load(f)
                            experiments.append({
                                "experiment_id": data["experiment_id"],
                                "timestamp": data["timestamp"],
                                "sample_id": data["sample_record"]["sample_id"],
                                "split": data["sample_record"]["split"],
                                "calibration_mode": data["evaluation_result"]["calibration"]["mode"],
                                "metrics": data["evaluation_result"]["metrics"],
                                "assets": data["evaluation_result"]["assets"]
                            })
                    except Exception as e:
                        logger.warning(f"Could not read experiment record in {exp_folder}: {e}")
        return experiments

    def get_experiment(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific experiment record by ID."""
        rec_file = self.experiments_dir / experiment_id / "experiment_record.json"
        if not rec_file.exists():
            return None
        with open(rec_file, "r") as f:
            return json.load(f)

    # -------------------------------------------------------------------------
    # Visualization & Diagnostic Renderers
    # -------------------------------------------------------------------------

    def _render_signed_error_png(self, error_map: np.ndarray, out_path: Path, sample_id: str, split: str) -> None:
        """Render diverging signed error heatmap (blue = underpredicted, red = overpredicted)."""
        fig = Figure(figsize=(8, 7), dpi=150)
        ax = fig.add_subplot(111)

        finite_vals = error_map[np.isfinite(error_map)]
        if len(finite_vals) > 0:
            limit = float(np.percentile(np.abs(finite_vals), 98.0))
            vmax = max(limit, 0.1)
            vmin = -vmax
        else:
            vmin, vmax = -1.0, 1.0

        cmap = matplotlib.colormaps["coolwarm"].with_extremes(bad="black")

        im = ax.imshow(error_map, cmap=cmap, vmin=vmin, vmax=vmax)
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("Signed Error (Predicted - Reference)", fontsize=10)

        ax.set_title(f"GAMUS Residual Error Map: {sample_id} ({split})", fontsize=11, fontweight="bold")
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(out_path, bbox_inches="tight")

    def _render_abs_error_png(self, error_map: np.ndarray, out_path: Path, sample_id: str, split: str) -> None:
        """Render sequential absolute error heatmap."""
        fig = Figure(figsize=(8, 7), dpi=150)
        ax = fig.add_subplot(111)

        finite_vals = error_map[np.isfinite(error_map)]
        if len(finite_vals) > 0:
            vmax = float(np.percentile(finite_vals, 98.0))
            vmax = max(vmax, 0.1)
        else:
            vmax = 1.0

        cmap = matplotlib.colormaps["magma"].with_extremes(bad="black")

        im = ax.imshow(error_map, cmap=cmap, vmin=0.0, vmax=vmax)
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("Absolute Error |Predicted - Reference|", fontsize=10)

        ax.set_title(f"GAMUS Absolute Error Map: {sample_id} ({split})", fontsize=11, fontweight="bold")
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(out_path, bbox_inches="tight")

    def _render_scatter_plot_png(
        self,
        pred_sub: np.ndarray,
        ref_sub: np.ndarray,
        metrics: GAMUSEvaluationMetrics,
        out_path: Path,
        sample_id: str,
        split: str,
        calib_mode: str
    ) -> None:
        """Render publication-quality scatter plot with regression and 1:1 identity line."""
        fig = Figure(figsize=(8, 7), dpi=150)
        ax = fig.add_subplot(111)

        # Scatter points
        ax.scatter(ref_sub, pred_sub, alpha=0.35, s=12, edgecolors="none", color="#2563EB", label="Sampled Pixels")

        # 1:1 Identity reference line
        all_vals = np.concatenate([pred_sub, ref_sub])
        min_v = float(np.min(all_vals))
        max_v = float(np.max(all_vals))
        ax.plot([min_v, max_v], [min_v, max_v], "r--", linewidth=1.8, label="1:1 Identity Reference")

        # Linear regression trend line
        if len(pred_sub) > 1:
            try:
                poly = np.polyfit(ref_sub, pred_sub, deg=1)
                x_line = np.linspace(min_v, max_v, 100)
                y_line = np.polyval(poly, x_line)
                ax.plot(x_line, y_line, "g-", linewidth=1.5, label=f"Fit (Slope: {poly[0]:.2f})")
            except Exception:
                pass

        # Diagnostic box
        unit_label = "m" if calib_mode != CalibrationMode.ZERO_SHOT_RELATIVE.value else "rel"
        diag_text = (
            f"MAE: {metrics.mae:.3f} {unit_label}\n"
            f"RMSE: {metrics.rmse:.3f} {unit_label}\n"
            f"Pearson r: {metrics.pearson_r:.3f}\n"
            f"Spearman ρ: {metrics.spearman_rho:.3f}\n"
            f"R²: {metrics.r2:.3f}\n"
            f"LE90: {metrics.le90:.3f} {unit_label}\n"
            f"N = {metrics.valid_pixels:,}"
        )
        ax.text(
            0.05, 0.95, diag_text,
            transform=ax.transAxes,
            verticalalignment="top",
            fontsize=9.5,
            family="monospace",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#F8FAFC", edgecolor="#CBD5E1", alpha=0.92)
        )

        ax.set_xlabel(f"Reference AGL Height ({unit_label})", fontsize=11, fontweight="bold")
        ax.set_ylabel(f"Predicted Height ({unit_label})", fontsize=11, fontweight="bold")
        ax.set_title(f"GAMUS Benchmark - {sample_id} ({split}) - Predicted vs Reference", fontsize=12, fontweight="bold")
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.legend(loc="lower right", framealpha=0.9)

        fig.tight_layout()
        fig.savefig(out_path, bbox_inches="tight")
