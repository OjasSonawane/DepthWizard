import logging
import os
import torch
import numpy as np
from PIL import Image
from typing import Optional, Union, Tuple
import cv2

from app.config import settings

logger = logging.getLogger("depthwizard.model")

class DepthEstimator:
    """
    Unified Monocular Depth Estimator for Remote Sensing & Aerial Imagery.
    Supports Depth Anything V2 / DPT models with automatic hardware acceleration
    (Apple Silicon MPS, NVIDIA CUDA, or CPU) and robust offline fallback.
    """
    _instance: Optional["DepthEstimator"] = None
    
    def __init__(self):
        self.device = settings.DEVICE
        self.model = None
        self.processor = None
        self.is_loaded = False
        self.is_fallback = False
        self.model_name = settings.MODEL_NAME
        self.torch_device = self._resolve_torch_device()

    def _resolve_torch_device(self) -> torch.device:
        if self.device == "cuda" and torch.cuda.is_available():
            return torch.device("cuda")
        elif self.device == "mps" and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")

    @classmethod
    def get_instance(cls) -> "DepthEstimator":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.load_model()
        return cls._instance

    def load_model(self):
        """Loads pretrained Depth Anything V2 model into memory."""
        if self.is_loaded:
            return

        logger.info(f"Initializing DepthEstimator '{self.model_name}' on device: {self.torch_device}")
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation

        # Try 1: Load from local Hugging Face cache
        try:
            logger.info(f"Attempting local cache load for {self.model_name}...")
            self.processor = AutoImageProcessor.from_pretrained(self.model_name, local_files_only=True)
            self.model = AutoModelForDepthEstimation.from_pretrained(self.model_name, local_files_only=True)
            self.model.to(self.torch_device)
            self.model.eval()
            self.is_loaded = True
            self.is_fallback = False
            logger.info(f"Successfully loaded {self.model_name} from local cache on {self.torch_device}")
            return
        except Exception as e_cache:
            logger.debug(f"Local cache hit failed ({e_cache}), trying online load...")

        # Try 2: Download / load from Hugging Face hub
        try:
            logger.info(f"Attempting online load for {self.model_name}...")
            self.processor = AutoImageProcessor.from_pretrained(self.model_name)
            self.model = AutoModelForDepthEstimation.from_pretrained(self.model_name)
            self.model.to(self.torch_device)
            self.model.eval()
            self.is_loaded = True
            self.is_fallback = False
            logger.info(f"Successfully downloaded and loaded {self.model_name} on {self.torch_device}")
            return
        except Exception as e_net:
            logger.error(f"Failed to load Depth Anything V2 weights from '{self.model_name}': {e_net}")
            raise RuntimeError(
                f"Depth Anything V2 model '{self.model_name}' could not be loaded. "
                f"Ensure weights are cached or network access is available. "
                f"No synthetic/heuristic placeholder terrain is permitted."
            ) from e_net

    def predict(self, image: Union[np.ndarray, Image.Image]) -> np.ndarray:
        """
        Estimates relative depth / elevation from input image using Depth Anything V2.
        Returns: 2D numpy array of shape (H, W) with float32 values in range [0.0, 1.0],
        where higher values represent higher elevation / closer terrain.
        """
        if not self.is_loaded:
            self.load_model()

        if self.model is None or self.processor is None:
            raise RuntimeError("Depth Anything V2 model is not loaded. Cannot execute depth estimation.")

        # Convert to PIL Image for consistency
        if isinstance(image, np.ndarray):
            if image.ndim == 2:
                pil_img = Image.fromarray(image).convert("RGB")
            elif image.ndim == 3:
                if image.shape[2] == 4:
                    pil_img = Image.fromarray(image[:, :, :3])
                else:
                    pil_img = Image.fromarray(image)
            else:
                raise ValueError(f"Unsupported image array dimensions: {image.shape}")
        else:
            pil_img = image.convert("RGB")

        orig_w, orig_h = pil_img.size

        # Run neural depth estimation
        inputs = self.processor(images=pil_img, return_tensors="pt").to(self.torch_device)
        with torch.no_grad():
            outputs = self.model(**inputs)
            predicted_depth = outputs.predicted_depth

        # Interpolate prediction to original image dimensions
        prediction = torch.nn.functional.interpolate(
            predicted_depth.unsqueeze(1),
            size=(orig_h, orig_w),
            mode="bicubic",
            align_corners=False,
        )
        raw_depth = prediction.squeeze(0).squeeze(0).cpu().numpy().astype(np.float32)

        # Normalize to [0.0, 1.0]
        norm_depth = self.normalize_depth(raw_depth)
        return norm_depth

    def normalize_depth(self, depth: np.ndarray) -> np.ndarray:
        """
        Normalizes depth array to [0.0, 1.0] range using robust percentile clipping (1st to 99th percentile).
        """
        valid_mask = np.isfinite(depth)
        if not np.any(valid_mask):
            return np.zeros_like(depth, dtype=np.float32)

        valid_vals = depth[valid_mask]
        p1 = float(np.percentile(valid_vals, 1.0))
        p99 = float(np.percentile(valid_vals, 99.0))

        if p99 > p1:
            clipped = np.clip(depth, p1, p99)
            norm = np.clip((clipped - p1) / (p99 - p1), 0.0, 1.0)
        else:
            norm = np.zeros_like(depth, dtype=np.float32)

        return norm.astype(np.float32)
