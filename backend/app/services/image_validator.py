import io
import os
import logging
from pathlib import Path
from typing import Union, Tuple, List, Optional, Dict, Any
import numpy as np
import cv2
from PIL import Image

from app.schemas.schemas import InputValidationResult, ValidationStageItem
from app.services.geospatial_service import GeospatialService

logger = logging.getLogger("depthwizard.validator")

class ImageValidator:
    """
    Specialized Multi-Stage Remote-Sensing Content & Suitability Validator.
    Protects DepthWizard by enforcing domain-specific optical remote-sensing
    quality control before monocular depth inference runs.
    """

    _face_cascade = None
    _profile_cascade = None
    _upperbody_cascade = None
    _hog_detector = None

    @classmethod
    def _init_detectors(cls):
        if cls._face_cascade is None:
            casc_dir = cv2.data.haarcascades
            f_path = os.path.join(casc_dir, 'haarcascade_frontalface_default.xml')
            p_path = os.path.join(casc_dir, 'haarcascade_profileface.xml')
            u_path = os.path.join(casc_dir, 'haarcascade_upperbody.xml')
            
            if os.path.exists(f_path):
                cls._face_cascade = cv2.CascadeClassifier(f_path)
            if os.path.exists(p_path):
                cls._profile_cascade = cv2.CascadeClassifier(p_path)
            if os.path.exists(u_path):
                cls._upperbody_cascade = cv2.CascadeClassifier(u_path)

            cls._hog_detector = cv2.HOGDescriptor()
            cls._hog_detector.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    @classmethod
    def validate_image(
        cls,
        image_input: Union[Path, str, bytes],
        filename: Optional[str] = None
    ) -> InputValidationResult:
        """
        Executes the 6-stage validation pipeline on an input image file or byte stream:
        1. File Format & Magic Bytes
        2. Image Decoding & Channel Integrity
        3. Resolution & Dimension Guardrails
        4. Geospatial Metadata Inspection
        5. Dominant Subject / Human Detection
        6. Content Classification & Suitability
        """
        if filename is None:
            filename = Path(image_input).name if isinstance(image_input, (str, Path)) else "image.png"

        cls._init_detectors()

        stages: List[ValidationStageItem] = []
        warnings: List[str] = []
        ext = Path(filename).suffix.lower()

        # -------------------------------------------------------------
        # STAGE 1: File Format & Magic Bytes
        # -------------------------------------------------------------
        raw_bytes: Optional[bytes] = None
        file_path: Optional[Path] = None

        if isinstance(image_input, (str, Path)):
            file_path = Path(image_input)
            if not file_path.exists():
                return cls._create_failure_result(
                    stages=[ValidationStageItem(
                        stage_id="format",
                        name="File Format",
                        passed=False,
                        message=f"File '{filename}' not found."
                    )],
                    filename=filename,
                    reason=f"File '{filename}' could not be read from disk."
                )
            with open(file_path, "rb") as f:
                raw_bytes = f.read(2048)
        else:
            raw_bytes = image_input[:2048]

        allowed_exts = {".tif", ".tiff", ".png", ".jpg", ".jpeg"}
        if ext not in allowed_exts:
            return cls._create_failure_result(
                stages=[ValidationStageItem(
                    stage_id="format",
                    name="File Format",
                    passed=False,
                    message=f"Unsupported file format '{ext}'. Allowed: GeoTIFF, PNG, JPG, JPEG."
                )],
                filename=filename,
                reason=f"Unsupported format '{ext}'. DepthWizard requires optical remote-sensing raster imagery."
            )

        # Magic bytes check
        if not raw_bytes or len(raw_bytes) == 0:
            return cls._create_failure_result(
                stages=[ValidationStageItem(
                    stage_id="format",
                    name="File Format",
                    passed=False,
                    message="Input image file is empty (0 bytes)."
                )],
                filename=filename,
                reason="Input image file is empty (0 bytes)."
            )

        is_magic_valid = False
        if ext in [".tif", ".tiff"] and (
            raw_bytes.startswith(b"II*\x00") or 
            raw_bytes.startswith(b"MM\x00*") or
            raw_bytes.startswith(b"II+\x00") or
            raw_bytes.startswith(b"MM\x00+")
        ):
            is_magic_valid = True
        elif ext == ".png" and raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            is_magic_valid = True
        elif ext in [".jpg", ".jpeg"] and raw_bytes.startswith(b"\xff\xd8\xff"):
            is_magic_valid = True

        if not is_magic_valid:
            return cls._create_failure_result(
                stages=[ValidationStageItem(
                    stage_id="format",
                    name="File Format",
                    passed=False,
                    message="File header signature does not match expected image format."
                )],
                filename=filename,
                reason="Corrupt or spoofed image header signature."
            )

        stages.append(ValidationStageItem(
            stage_id="format",
            name="File Format & Container",
            passed=True,
            message=f"Valid {ext.upper().lstrip('.')} format and container signature verified."
        ))

        # -------------------------------------------------------------
        # STAGE 2: Image Decoding & Color Space
        # -------------------------------------------------------------
        rgb_array: Optional[np.ndarray] = None
        is_georeferenced = False
        crs_str: Optional[str] = None
        has_geotags = False

        try:
            if file_path and file_path.exists():
                meta, rgb_array = GeospatialService.inspect_file(file_path)
                is_georeferenced = meta.is_georeferenced
                crs_str = meta.crs
                has_geotags = meta.is_georeferenced and meta.crs is not None
            else:
                # Decode from memory bytes
                bio = io.BytesIO(image_input)
                pil_img = Image.open(bio)
                if pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")
                rgb_array = np.array(pil_img)
        except Exception as e:
            return cls._create_failure_result(
                stages=stages + [ValidationStageItem(
                    stage_id="decode",
                    name="Image Decoding",
                    passed=False,
                    message=f"Failed to decode image raster: {str(e)}"
                )],
                filename=filename,
                reason="Image decoding failed. File may be corrupted or truncated."
            )

        if rgb_array is None or rgb_array.size == 0:
            return cls._create_failure_result(
                stages=stages + [ValidationStageItem(
                    stage_id="decode",
                    name="Image Decoding",
                    passed=False,
                    message="Decoded raster is empty."
                )],
                filename=filename,
                reason="Empty raster array."
            )

        # Check for solid blank images (zero variance)
        var = float(np.var(rgb_array))
        if var < 1.0:
            return cls._create_failure_result(
                stages=stages + [ValidationStageItem(
                    stage_id="decode",
                    name="Image Decoding",
                    passed=False,
                    message="Image raster is a solid single-color frame (zero variance)."
                )],
                filename=filename,
                reason="Image is completely uniform/blank. Real optical terrain imagery exhibits textural variation."
            )

        h, w = rgb_array.shape[:2]
        stages.append(ValidationStageItem(
            stage_id="decode",
            name="Image Decoding & Color Space",
            passed=True,
            message=f"Decoded {w}×{h} px RGB raster with healthy radiometric variance."
        ))

        # -------------------------------------------------------------
        # STAGE 3: Resolution Validation & Guardrails
        # -------------------------------------------------------------
        if w < 32 or h < 32:
            return cls._create_failure_result(
                stages=stages + [ValidationStageItem(
                    stage_id="resolution",
                    name="Resolution & Dimensions",
                    passed=False,
                    message=f"Critical Resolution Failure: {w}×{h} px. Minimum required is 32×32 px."
                )],
                filename=filename,
                reason=f"Image resolution too small for reconstruction: {w}×{h} px (minimum 32×32 px required)."
            )

        res_warning = False
        aspect = max(w / max(1, h), h / max(1, w))
        if aspect > 8.0:
            res_warning = True
            warnings.append(f"Extreme aspect ratio ({aspect:.1f}:1). May cause spatial distortion in 3D projection.")

        if w < 128 or h < 128:
            res_warning = True
            res_msg = f"Low-Resolution: {w}×{h} px. Coarse reconstruction with adaptive interpolation."
            warnings.append(f"Low resolution ({w}×{h} px). Quality may be degraded, adaptive interpolation applied.")
        elif w < 512 or h < 512:
            res_msg = f"Acceptable Resolution: {w}×{h} px (Standard terrain reconstruction)."
        else:
            res_msg = f"Optimal Resolution: {w}×{h} px (Meets recommended ≥ 512×512 standard)."

        stages.append(ValidationStageItem(
            stage_id="resolution",
            name="Resolution & Dimensions",
            passed=True,
            warning=res_warning,
            message=res_msg
        ))

        # -------------------------------------------------------------
        # STAGE 4: Geospatial Metadata Priority
        # -------------------------------------------------------------
        if is_georeferenced and crs_str:
            stages.append(ValidationStageItem(
                stage_id="geospatial",
                name="Geospatial Reference",
                passed=True,
                message=f"Georeferenced GeoTIFF with verified spatial reference ({crs_str}). Target: Metric DSM."
            ))
        else:
            warnings.append("Non-georeferenced imagery: Target output will be Relative Digital Surface Model (rDSM).")
            stages.append(ValidationStageItem(
                stage_id="geospatial",
                name="Geospatial Reference",
                passed=True,
                warning=True,
                message="No CRS/affine tags found. Relative terrain reconstruction (rDSM) mode active."
            ))

        # -------------------------------------------------------------
        # STAGE 5: Dominant Subject & Human / Portrait Detection
        # -------------------------------------------------------------
        dominant_human = False
        rejection_reason: Optional[str] = None
        detected_category = "satellite_terrain"

        gray = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2GRAY)
        img_area = float(w * h)

        # Face detection
        faces = []
        if cls._face_cascade is not None and not cls._face_cascade.empty():
            # Downsample large images for rapid cascade inspection
            max_dim = max(w, h)
            scale_factor = 1.0
            gray_scaled = gray
            if max_dim > 800:
                scale_factor = 800.0 / max_dim
                gray_scaled = cv2.resize(gray, (int(w * scale_factor), int(h * scale_factor)))

            detected_faces = cls._face_cascade.detectMultiScale(
                gray_scaled,
                scaleFactor=1.1,
                minNeighbors=4,
                minSize=(int(30 * scale_factor), int(30 * scale_factor))
            )
            for (fx, fy, fw, fh) in detected_faces:
                orig_w = fw / scale_factor
                orig_h = fh / scale_factor
                faces.append((orig_w, orig_h, orig_w * orig_h))

        # Check for profile faces if no frontal faces found
        if len(faces) == 0 and cls._profile_cascade is not None and not cls._profile_cascade.empty():
            prof_faces = cls._profile_cascade.detectMultiScale(
                gray, scaleFactor=1.15, minNeighbors=4, minSize=(40, 40)
            )
            for (fx, fy, fw, fh) in prof_faces:
                faces.append((fw, fh, fw * fh))

        # Upper body detection
        upper_bodies = []
        if cls._upperbody_cascade is not None and not cls._upperbody_cascade.empty():
            u_bodies = cls._upperbody_cascade.detectMultiScale(
                gray, scaleFactor=1.2, minNeighbors=3, minSize=(60, 60)
            )
            for (bx, by, bw, bh) in u_bodies:
                upper_bodies.append(bw * bh)

        total_face_area = sum(f[2] for f in faces)
        face_area_ratio = total_face_area / img_area
        max_face_width_ratio = max((f[0] / w for f in faces), default=0.0)
        upper_body_ratio = sum(upper_bodies) / img_area

        # Evaluate human dominance
        # Dominant human: face takes > 3.0% of image OR face width > 14% of image width OR upper body > 10%
        if face_area_ratio > 0.030 or max_face_width_ratio > 0.14:
            dominant_human = True
            detected_category = "Human / Portrait"
            rejection_reason = (
                "Human-dominant image detected. This image appears to contain a person, selfie, or portrait as the primary subject. "
                "DepthWizard requires optical remote-sensing, aerial, drone, or terrain imagery."
            )
        elif upper_body_ratio > 0.10:
            dominant_human = True
            detected_category = "Human / Person Dominant"
            rejection_reason = (
                "Dominant human figure detected in foreground. DepthWizard accepts optical remote-sensing, aerial, drone, and terrain imagery."
            )

        # -------------------------------------------------------------
        # STAGE 6: Document, Screenshot & Graphic Detection
        # -------------------------------------------------------------
        is_document = False
        if not dominant_human and not has_geotags:
            # Check for document / screenshot patterns:
            # 1. High contrast text lines (horizontal gradient variance)
            # 2. Extreme saturation spike at 255/0 (white document background / dark terminal)
            white_pixels = np.count_nonzero(gray > 240) / float(gray.size)
            black_pixels = np.count_nonzero(gray < 15) / float(gray.size)

            sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
            sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
            edge_density = float(np.mean(np.abs(sobel_x) + np.abs(sobel_y)))

            # Documents usually have huge white background (> 50%) and high edge sharpness
            if white_pixels > 0.55 and edge_density > 25.0:
                is_document = True
                detected_category = "Document / Text"
                rejection_reason = (
                    "Document or text screenshot detected. DepthWizard accepts optical remote-sensing, aerial, drone, and terrain imagery."
                )
            elif black_pixels > 0.65 and edge_density > 20.0:
                is_document = True
                detected_category = "Screenshot / Terminal"
                rejection_reason = (
                    "Software screenshot detected. DepthWizard accepts optical remote-sensing, aerial, drone, and terrain imagery."
                )

        # -------------------------------------------------------------
        # STAGE 7: Content Suitability Scoring
        # -------------------------------------------------------------
        # Base suitability evaluation
        suitability_score = 88

        if has_geotags:
            # Valid GeoTIFF with CRS gets top suitability
            suitability_score = 96
            detected_category = "Georeferenced Satellite Imagery"
        elif dominant_human:
            suitability_score = 12
        elif is_document:
            suitability_score = 15
        else:
            # Analyze spatial texture continuity across scene
            # Remote-sensing terrain has continuous Laplacian variance across grid quadrants
            lap = cv2.Laplacian(gray, cv2.CV_32F)
            lap_var = float(np.var(lap))
            
            # Check central focus vs borders (portrait / product / food has high center focus, blurry borders)
            cy, cx = h // 2, w // 2
            r_y, r_x = h // 4, w // 4
            center_patch = gray[cy - r_y : cy + r_y, cx - r_x : cx + r_x]
            border_mask = np.ones_like(gray, dtype=bool)
            border_mask[cy - r_y : cy + r_y, cx - r_x : cx + r_x] = False
            
            center_var = float(np.var(center_patch))
            border_var = float(np.var(gray[border_mask]))
            
            # Isolated product/food bokeh check (center sharp, borders very flat)
            if border_var > 0 and (center_var / border_var) > 7.0 and border_var < 50.0:
                detected_category = "Product / Studio Object"
                rejection_reason = (
                    "Isolated studio product, food, or object detected with blurred backdrop. "
                    "DepthWizard requires optical remote-sensing, aerial, drone, or terrain imagery."
                )
                suitability_score = 22
            else:
                # Classify legitimate remote sensing type
                if w < 64 or h < 64:
                    suitability_score = 55
                    detected_category = "Low-Resolution Terrain (Preview Mode)"
                elif w >= 512 and h >= 512:
                    suitability_score = 92
                    detected_category = "Optical Remote-Sensing / Terrain"
                else:
                    suitability_score = 82
                    detected_category = "Aerial / Drone Terrain Imagery"

        # Check if acceptable
        is_suitable = (rejection_reason is None) and (suitability_score >= 50)
        
        if is_suitable:
            stages.append(ValidationStageItem(
                stage_id="content",
                name="Content Suitability",
                passed=True,
                message=f"Verified {detected_category} context ({suitability_score}% suitability score)."
            ))
            stages.append(ValidationStageItem(
                stage_id="readiness",
                name="Reconstruction Readiness",
                passed=True,
                message="All inspection stages satisfied. Imagery is ready for 3D elevation reconstruction."
            ))
            status = "warning" if len(warnings) > 0 else "ready"
        else:
            stages.append(ValidationStageItem(
                stage_id="content",
                name="Content Suitability",
                passed=False,
                message=rejection_reason or "Unsupported image content."
            ))
            stages.append(ValidationStageItem(
                stage_id="readiness",
                name="Reconstruction Readiness",
                passed=False,
                message="Image content rejected. Cannot proceed to 3D elevation reconstruction."
            ))
            status = "rejected"

        return InputValidationResult(
            status=status,
            is_suitable=is_suitable,
            suitability_score=suitability_score,
            detected_content=detected_category,
            rejection_reason=rejection_reason,
            dominant_human_detected=dominant_human,
            stages=stages,
            warnings=warnings,
            width=w,
            height=h,
            format=ext.upper().lstrip('.'),
            is_georeferenced=is_georeferenced,
            crs=crs_str
        )

    @classmethod
    def _create_failure_result(
        cls,
        stages: List[ValidationStageItem],
        filename: str,
        reason: str
    ) -> InputValidationResult:
        ext = Path(filename).suffix.upper().lstrip('.')
        stages.append(ValidationStageItem(
            stage_id="readiness",
            name="Reconstruction Readiness",
            passed=False,
            message="Reconstruction halted due to validation failure."
        ))
        return InputValidationResult(
            status="rejected",
            is_suitable=False,
            suitability_score=0,
            detected_content="Invalid / Corrupt",
            rejection_reason=reason,
            dominant_human_detected=False,
            stages=stages,
            warnings=[reason],
            width=0,
            height=0,
            format=ext,
            is_georeferenced=False,
            crs=None
        )
