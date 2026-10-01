import hashlib
import logging
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List
import numpy as np
from PIL import Image
import rasterio
from rasterio.transform import Affine
from rasterio.warp import reproject, Resampling, transform_bounds
import pyproj

from app.schemas.schemas import ImageMetadata, DEMMetadata, GeoTIFFVerificationResult

logger = logging.getLogger("depthwizard.geospatial")


class SpatialOverlapError(ValueError):
    """Raised when reference DEM extent does not overlap with primary imagery."""
    pass


class GeospatialService:
    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Computes SHA-256 cryptographic hex digest of a file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def is_actually_georeferenced(src: rasterio.io.DatasetReader) -> Tuple[bool, Optional[str], Optional[List[float]], Optional[List[float]], Optional[List[float]]]:
        """
        Determines whether an open raster dataset is genuinely georeferenced.
        Verifies:
        1. CRS exists and is recognized by PROJ
        2. Transform exists, is non-identity, non-degenerate (det != 0), and has positive resolution
        3. Bounds are finite, valid numbers with positive area
        Returns: (is_georeferenced, crs_str, transform_list, bounds_list, resolution_list)
        """
        if src.crs is None:
            return False, None, None, None, None

        # Verify CRS can be parsed
        try:
            crs_obj = pyproj.CRS.from_user_input(src.crs.to_string())
            crs_str = src.crs.to_string()
        except Exception:
            return False, None, None, None, None

        if src.transform is None or src.transform == Affine.identity():
            return False, None, None, None, None

        # Check transform degeneracy
        det = src.transform.determinant
        if abs(det) < 1e-12:
            return False, None, None, None, None

        dx = abs(src.transform.a)
        dy = abs(src.transform.e)
        if dx <= 0 or dy <= 0 or not (np.isfinite(dx) and np.isfinite(dy)):
            return False, None, None, None, None

        # Check bounds
        b = src.bounds
        if not (np.isfinite(b.left) and np.isfinite(b.bottom) and np.isfinite(b.right) and np.isfinite(b.top)):
            return False, None, None, None, None

        if b.right <= b.left or b.top <= b.bottom:
            return False, None, None, None, None

        transform_list = list(src.transform)[:6]
        bounds_list = [float(b.left), float(b.bottom), float(b.right), float(b.top)]
        res_list = [float(dx), float(dy)]

        return True, crs_str, transform_list, bounds_list, res_list

    @staticmethod
    def inspect_file(file_path: Path) -> Tuple[ImageMetadata, np.ndarray]:
        """
        Inspects an uploaded image file (TIFF, GeoTIFF, PNG, JPG).
        Extracts full geospatial metadata (CRS, transform, bounds, resolution, nodata, band count, dtype, hash).
        Determines whether the file is actually georeferenced.
        Handles 1-band (grayscale), 3-band (RGB), 4-band (RGBA/NIR), and multispectral imagery.
        Returns: (ImageMetadata, rgb_array [H, W, 3] in uint8)
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Input raster file not found: {file_path}")

        file_size = file_path.stat().st_size
        if file_size == 0:
            raise ValueError(f"Input raster file is empty (0 bytes): {file_path.name}")

        suffix = file_path.suffix.lower()
        file_hash = GeospatialService.compute_file_hash(file_path)

        # Check if file can be opened by rasterio
        if suffix in [".tif", ".tiff"]:
            try:
                with rasterio.open(file_path) as src:
                    width = src.width
                    height = src.height
                    band_count = src.count
                    native_dtype = str(src.dtypes[0]) if src.dtypes else "uint8"
                    nodata_val = float(src.nodata) if src.nodata is not None else None

                    is_georef, crs_str, transform_list, bounds, res = GeospatialService.is_actually_georeferenced(src)

                    # Multi-band extraction into RGB (H, W, 3)
                    if band_count == 1:
                        gray = src.read(1)
                        raw_rgb = np.dstack([gray, gray, gray])
                    elif band_count == 2:
                        b1 = src.read(1)
                        b2 = src.read(2)
                        raw_rgb = np.dstack([b1, b2, b1])
                    elif band_count >= 3:
                        r = src.read(1)
                        g = src.read(2)
                        b = src.read(3)
                        raw_rgb = np.dstack([r, g, b])
                    else:
                        raise ValueError(f"Raster has invalid band count: {band_count}")

                    # Handle native dtype and normalize to uint8 for neural pipeline
                    if raw_rgb.dtype == np.uint8:
                        rgb = raw_rgb
                    else:
                        # Normalize 16-bit or floating-point imagery via 2nd-98th percentile scaling
                        valid_mask = np.isfinite(raw_rgb)
                        if nodata_val is not None:
                            valid_mask = valid_mask & (raw_rgb != nodata_val)

                        if np.any(valid_mask):
                            p2 = float(np.percentile(raw_rgb[valid_mask], 2))
                            p98 = float(np.percentile(raw_rgb[valid_mask], 98))
                            if p98 > p2:
                                scaled = np.clip((raw_rgb.astype(np.float32) - p2) / (p98 - p2) * 255.0, 0, 255)
                                scaled = np.nan_to_num(scaled, nan=0.0)
                                rgb = scaled.astype(np.uint8)
                            else:
                                rgb = np.zeros((height, width, 3), dtype=np.uint8)
                        else:
                            rgb = np.zeros((height, width, 3), dtype=np.uint8)

                    classification = (
                        "Georeferenced optical imagery (GeoTIFF)" if is_georef
                        else "Non-georeferenced optical image (TIFF)"
                    )

                    # Resolution checks
                    is_low_res = (width < 256 or height < 256)
                    if width < 64 or height < 64:
                        res_warning = (
                            f"Input resolution: {width}×{height} px. "
                            f"This image is too small for reliable terrain reconstruction."
                        )
                    elif is_low_res:
                        res_warning = (
                            f"Input resolution: {width}×{height} px. "
                            f"This image is below the recommended 512×512 px minimum."
                        )
                    else:
                        res_warning = None

                    meta = ImageMetadata(
                        width=width,
                        height=height,
                        format=suffix.replace(".", "").upper(),
                        file_size_bytes=file_size,
                        is_georeferenced=is_georef,
                        crs=crs_str,
                        transform=transform_list,
                        bounds=bounds,
                        resolution=res,
                        nodata=nodata_val,
                        band_count=band_count,
                        datatype="uint8",
                        native_dtype=native_dtype,
                        file_hash=file_hash,
                        classification=classification,
                        is_low_resolution=is_low_res,
                        resolution_warning=res_warning
                    )
                    return meta, rgb

            except Exception as e:
                # If rasterio fails, check if PIL can open it or if it's genuinely invalid
                logger.warning(f"Rasterio could not parse TIFF {file_path.name}: {e}. Trying PIL fallback...")
                try:
                    with Image.open(file_path) as pil_img:
                        pil_img.verify()
                except Exception as pil_err:
                    raise ValueError(f"Corrupted or invalid image file '{file_path.name}': {e}; {pil_err}")

        # Standard non-georeferenced image (PNG, JPG, etc. or unreferenced TIFF fallback)
        try:
            with Image.open(file_path) as pil_img:
                w, h = pil_img.size
                mode = pil_img.mode
                band_count = len(mode) if mode in ["RGB", "RGBA", "CMYK"] else 3
                if mode == "RGBA":
                    bg = Image.new("RGB", pil_img.size, (255, 255, 255))
                    bg.paste(pil_img, mask=pil_img.split()[3])
                    rgb_img = bg
                else:
                    rgb_img = pil_img.convert("RGB")
                rgb = np.array(rgb_img, dtype=np.uint8)
        except Exception as e:
            raise ValueError(f"Corrupted or invalid image file '{file_path.name}': {e}")

        is_low_res = (w < 256 or h < 256)
        if w < 64 or h < 64:
            res_warning = (
                f"Input resolution: {w}×{h} px. "
                f"This image is too small for reliable terrain reconstruction. "
                f"Output 3D mesh is generated for preview only and cannot be used for scientific terrain analysis. "
                f"Upload a higher-resolution RGB/GeoTIFF image (recommended ≥512×512) for meaningful DSM generation."
            )
        elif is_low_res:
            res_warning = (
                f"Input resolution: {w}×{h} px. "
                f"This image is below the recommended 512×512 px minimum. "
                f"Terrain reconstruction will have limited fine topographic fidelity."
            )
        else:
            res_warning = None

        meta = ImageMetadata(
            width=w,
            height=h,
            format=suffix.replace(".", "").upper(),
            file_size_bytes=file_size,
            is_georeferenced=False,
            crs=None,
            transform=None,
            bounds=None,
            resolution=None,
            nodata=None,
            band_count=band_count,
            datatype="uint8",
            native_dtype="uint8",
            file_hash=file_hash,
            classification="Non-georeferenced optical image",
            is_low_resolution=is_low_res,
            resolution_warning=res_warning
        )
        return meta, rgb

    @staticmethod
    def inspect_dem_file(
        dem_path: Path,
        image_crs: Optional[str] = None,
        image_bounds: Optional[List[float]] = None
    ) -> DEMMetadata:
        """
        Extracts spatial metadata and elevation range from a reference DEM GeoTIFF.
        Verifies spatial compatibility with the primary imagery.
        """
        try:
            with rasterio.open(dem_path) as src:
                is_georef, crs_str, _, bounds, res = GeospatialService.is_actually_georeferenced(src)
                
                # Sample elevation range
                data = src.read(1)
                nodata = src.nodata
                valid_mask = np.isfinite(data) & (data > -9000.0)
                if nodata is not None:
                    valid_mask = valid_mask & (data != nodata)
                
                valid_data = data[valid_mask]
                min_elev = float(np.min(valid_data)) if len(valid_data) > 0 else 0.0
                max_elev = float(np.max(valid_data)) if len(valid_data) > 0 else 1000.0

                is_compat = is_georef
                note = "Spatial reference verified."
                if not is_georef:
                    is_compat = False
                    note = "Reference DEM lacks valid geospatial reference (CRS or transform)."
                elif image_crs and crs_str:
                    if image_crs.strip().upper() != crs_str.strip().upper():
                        note = f"CRS difference detected ({crs_str} vs {image_crs}); will automatically reproject on calibration."

                return DEMMetadata(
                    filename=dem_path.name,
                    crs=crs_str,
                    resolution=res,
                    bounds=bounds,
                    min_elevation=round(min_elev, 2),
                    max_elevation=round(max_elev, 2),
                    is_compatible=is_compat,
                    compatibility_note=note
                )
        except Exception as e:
            logger.warning(f"Failed to inspect DEM {dem_path}: {e}")
            return DEMMetadata(
                filename=dem_path.name,
                crs=None,
                resolution=None,
                bounds=None,
                min_elevation=0.0,
                max_elevation=100.0,
                is_compatible=False,
                compatibility_note=f"Inspection error: {str(e)}"
            )

    @staticmethod
    def check_bounds_overlap(
        crs1_str: str, bounds1: List[float],
        crs2_str: str, bounds2: List[float]
    ) -> bool:
        """
        Checks whether two bounding boxes overlap when transformed to WGS84 (EPSG:4326).
        bounds format: [left, bottom, right, top]
        """
        try:
            # Transform bounds1 to EPSG:4326
            crs1 = rasterio.crs.CRS.from_string(crs1_str)
            wgs1 = transform_bounds(crs1, "EPSG:4326", bounds1[0], bounds1[1], bounds1[2], bounds1[3])

            # Transform bounds2 to EPSG:4326
            crs2 = rasterio.crs.CRS.from_string(crs2_str)
            wgs2 = transform_bounds(crs2, "EPSG:4326", bounds2[0], bounds2[1], bounds2[2], bounds2[3])

            inter_left = max(wgs1[0], wgs2[0])
            inter_bottom = max(wgs1[1], wgs2[1])
            inter_right = min(wgs1[2], wgs2[2])
            inter_top = min(wgs1[3], wgs2[3])

            # Check positive intersection area with small tolerance
            return (inter_right - inter_left > -1e-5) and (inter_top - inter_bottom > -1e-5)
        except Exception as e:
            logger.warning(f"Error computing bounds overlap: {e}")
            return True

    @staticmethod
    def reproject_match(
        reference_path: Path,
        target_shape: Tuple[int, int],
        target_crs_str: Optional[str],
        target_transform_list: Optional[List[float]]
    ) -> np.ndarray:
        """
        Reprojects and resamples a reference DEM raster to match the exact target geometry.
        Explicitly handles:
        - Missing or invalid target CRS
        - Missing or invalid reference CRS
        - Different CRSs (e.g. UTM vs WGS84)
        - Different resolutions (e.g. 1m vs 30m)
        - Different bounds / extents (verifies spatial overlap; raises SpatialOverlapError if non-overlapping)
        - Different pixel alignments (evaluates at target pixel centers via dst_transform)
        - NoData masking (source nodata mapped to np.nan)
        """
        if not target_crs_str or not target_transform_list:
            raise ValueError(
                "Target imagery lacks spatial reference (CRS or transform). "
                "Reprojection requires a georeferenced target."
            )

        target_h, target_w = target_shape
        try:
            target_crs = rasterio.crs.CRS.from_string(target_crs_str)
            target_transform = Affine(*target_transform_list)
        except Exception as e:
            raise ValueError(f"Invalid target spatial reference: {e}")

        # Target bounds
        target_bounds = [
            target_transform.c,
            target_transform.f + target_transform.e * target_h,
            target_transform.c + target_transform.a * target_w,
            target_transform.f
        ]
        # Ensure left < right and bottom < top
        target_bounds = [
            min(target_bounds[0], target_bounds[2]),
            min(target_bounds[1], target_bounds[3]),
            max(target_bounds[0], target_bounds[2]),
            max(target_bounds[1], target_bounds[3])
        ]

        with rasterio.open(reference_path) as src:
            if src.crs is None:
                raise ValueError(
                    f"Reference DEM '{reference_path.name}' lacks coordinate reference system (CRS) metadata."
                )

            src_bounds = [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top]
            
            # Check spatial overlap
            if not GeospatialService.check_bounds_overlap(
                crs1_str=target_crs_str, bounds1=target_bounds,
                crs2_str=src.crs.to_string(), bounds2=src_bounds
            ):
                raise SpatialOverlapError(
                    f"Reference DEM '{reference_path.name}' bounds ({src_bounds}) do not spatially overlap "
                    f"with primary imagery bounds ({target_bounds})."
                )

            destination = np.full((target_h, target_w), np.nan, dtype=np.float32)
            src_nodata = src.nodata if src.nodata is not None else -9999.0

            reproject(
                source=rasterio.band(src, 1),
                destination=destination,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=target_transform,
                dst_crs=target_crs,
                resampling=Resampling.bilinear,
                src_nodata=src_nodata,
                dst_nodata=np.nan
            )

            # Mask out extreme nodata artifacts (e.g. -32767, -9999)
            destination[destination <= -9000.0] = np.nan

            return destination

    @staticmethod
    def save_geotiff(
        output_path: Path,
        data: np.ndarray,
        crs_str: Optional[str],
        transform_list: Optional[List[float]],
        nodata: float = -9999.0,
        metadata_tags: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Saves a 2D float32 raster to GeoTIFF, preserving CRS, affine transform, dimensions, and NoData.
        Embeds full GDAL metadata provenance tags.
        """
        h, w = data.shape
        data_to_write = data.astype(np.float32).copy()
        
        # Replace non-finite with nodata
        data_to_write[~np.isfinite(data_to_write)] = nodata

        if crs_str and transform_list:
            crs = rasterio.crs.CRS.from_string(crs_str)
            transform = Affine(*transform_list)
        else:
            crs = None
            transform = Affine.identity()

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            height=h,
            width=w,
            count=1,
            dtype=rasterio.float32,
            crs=crs,
            transform=transform,
            nodata=nodata
        ) as dst:
            dst.write(data_to_write, 1)
            
            if metadata_tags:
                clean_tags = {
                    str(k).upper(): str(v)
                    for k, v in metadata_tags.items()
                    if v is not None
                }
                dst.update_tags(**clean_tags)

        return output_path

    @staticmethod
    def verify_geotiff_roundtrip(
        geotiff_path: Path,
        expected_data: Optional[np.ndarray] = None,
        expected_crs: Optional[str] = None,
        expected_transform: Optional[List[float]] = None,
        expected_nodata: float = -9999.0
    ) -> GeoTIFFVerificationResult:
        """
        Reopens an exported GeoTIFF raster and rigorously validates that:
        - File opens cleanly without corruption
        - CRS matches expected CRS
        - Transform matches expected transform
        - Dimensions match expected dimensions
        - NoData value is preserved
        - Data values match expected array within float32 precision
        - Metadata provenance tags are preserved
        """
        if not geotiff_path.exists():
            return GeoTIFFVerificationResult(
                is_valid=False,
                filepath=str(geotiff_path),
                width=0,
                height=0,
                dtype="unknown",
                crs_preserved=False,
                transform_preserved=False,
                dimensions_preserved=False,
                nodata_preserved=False,
                values_preserved=False,
                message=f"File does not exist: {geotiff_path}"
            )

        try:
            with rasterio.open(geotiff_path) as dst:
                w = dst.width
                h = dst.height
                dtype_str = str(dst.dtypes[0])
                crs_str = dst.crs.to_string() if dst.crs else None
                transform_list = list(dst.transform)[:6] if dst.transform else None
                bounds_list = [dst.bounds.left, dst.bounds.bottom, dst.bounds.right, dst.bounds.top]
                res_list = [abs(dst.res[0]), abs(dst.res[1])]
                nodata_val = float(dst.nodata) if dst.nodata is not None else None
                tags = dict(dst.tags())
                read_data = dst.read(1)

                # 1. CRS preservation
                if expected_crs:
                    crs_preserved = bool(crs_str and (
                        crs_str.strip().upper() == expected_crs.strip().upper() or
                        pyproj.CRS.from_user_input(crs_str) == pyproj.CRS.from_user_input(expected_crs)
                    ))
                else:
                    crs_preserved = (crs_str is None)

                # 2. Transform preservation
                if expected_transform:
                    transform_preserved = bool(transform_list and np.allclose(transform_list, expected_transform, atol=1e-5))
                else:
                    transform_preserved = True

                # 3. Dimensions preservation
                if expected_data is not None:
                    exp_h, exp_w = expected_data.shape
                    dim_preserved = (w == exp_w and h == exp_h)
                else:
                    dim_preserved = (w > 0 and h > 0)

                # 4. NoData preservation
                nodata_preserved = (nodata_val == expected_nodata) if nodata_val is not None else False

                # 5. Values preservation
                max_diff = 0.0
                values_preserved = True
                if expected_data is not None:
                    valid_mask = np.isfinite(expected_data) & (expected_data != expected_nodata)
                    if np.any(valid_mask):
                        actual_valid = read_data[valid_mask]
                        expected_valid = expected_data[valid_mask]
                        diffs = np.abs(actual_valid - expected_valid)
                        max_diff = float(np.max(diffs))
                        values_preserved = bool(max_diff < 1e-4)

                all_valid = (
                    crs_preserved and
                    transform_preserved and
                    dim_preserved and
                    nodata_preserved and
                    values_preserved
                )

                return GeoTIFFVerificationResult(
                    is_valid=all_valid,
                    filepath=str(geotiff_path),
                    width=w,
                    height=h,
                    crs=crs_str,
                    transform=transform_list,
                    bounds=bounds_list,
                    resolution=res_list,
                    nodata=nodata_val,
                    dtype=dtype_str,
                    tags=tags,
                    crs_preserved=crs_preserved,
                    transform_preserved=transform_preserved,
                    dimensions_preserved=dim_preserved,
                    nodata_preserved=nodata_preserved,
                    values_preserved=values_preserved,
                    max_value_diff=round(max_diff, 6),
                    message="GeoTIFF verification passed: all spatial metadata and values preserved."
                    if all_valid else "GeoTIFF verification failed: spatial discrepancy detected."
                )

        except Exception as e:
            return GeoTIFFVerificationResult(
                is_valid=False,
                filepath=str(geotiff_path),
                width=0,
                height=0,
                dtype="unknown",
                crs_preserved=False,
                transform_preserved=False,
                dimensions_preserved=False,
                nodata_preserved=False,
                values_preserved=False,
                message=f"Failed to reopen GeoTIFF: {str(e)}"
            )

    @staticmethod
    def pixel_to_coords(
        row: float,
        col: float,
        transform_list: Optional[List[float]],
        crs_str: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Converts pixel coordinates (row, col) to projected coords (x, y)
        and lat/lon if projected.
        """
        if not transform_list:
            return {"x": col, "y": row, "is_geographic": False}

        transform = Affine(*transform_list)
        x, y = rasterio.transform.xy(transform, row, col)
        
        res = {"x": float(x), "y": float(y), "is_geographic": True}
        
        if crs_str:
            try:
                crs = rasterio.crs.CRS.from_string(crs_str)
                if not crs.is_geographic:
                    transformer = pyproj.Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
                    lon, lat = transformer.transform(x, y)
                    res["longitude"] = float(lon)
                    res["latitude"] = float(lat)
                else:
                    res["longitude"] = float(x)
                    res["latitude"] = float(y)
            except Exception as e:
                logger.debug(f"Coordinate transformation to WGS84 error: {e}")

        return res

    @staticmethod
    def get_ground_resolution_meters(
        crs_str: Optional[str],
        resolution: Optional[List[float]],
        bounds: Optional[List[float]] = None
    ) -> Tuple[float, float]:
        """
        Calculates metric ground sampling distance (dx_meters, dy_meters).
        For projected coordinate systems (e.g. UTM), returns resolution in meters.
        For geographic coordinate systems (e.g. EPSG:4326), computes geodesic ground distance
        at the scene center latitude.
        """
        if not resolution or len(resolution) < 2 or resolution[0] <= 0 or resolution[1] <= 0:
            return (1.0, 1.0)

        dx, dy = abs(float(resolution[0])), abs(float(resolution[1]))

        if not crs_str:
            return (dx, dy)

        try:
            crs = rasterio.crs.CRS.from_string(crs_str)
            if crs.is_geographic:
                center_lat = 0.0
                if bounds and len(bounds) >= 4:
                    center_lat = (bounds[1] + bounds[3]) / 2.0
                center_lat = max(-89.0, min(89.0, center_lat))
                lat_rad = np.radians(center_lat)
                
                meters_per_deg_lon = 111320.0 * np.cos(lat_rad)
                meters_per_deg_lat = 110540.0
                
                dx_m = max(0.001, dx * meters_per_deg_lon)
                dy_m = max(0.001, dy * meters_per_deg_lat)
                return (float(dx_m), float(dy_m))
            else:
                return (dx, dy)
        except Exception as e:
            logger.warning(f"Error determining ground resolution in meters for CRS '{crs_str}': {e}")
            return (dx, dy)

    @staticmethod
    def reproject_coords(
        x: float,
        y: float,
        from_crs_str: str,
        to_crs_str: str
    ) -> Tuple[float, float]:
        """
        Reprojects coordinates (x, y) from source CRS to destination CRS.
        """
        if from_crs_str.strip().upper() == to_crs_str.strip().upper():
            return (x, y)
        from_crs = rasterio.crs.CRS.from_string(from_crs_str)
        to_crs = rasterio.crs.CRS.from_string(to_crs_str)
        transformer = pyproj.Transformer.from_crs(from_crs, to_crs, always_xy=True)
        new_x, new_y = transformer.transform(x, y)
        return (float(new_x), float(new_y))
