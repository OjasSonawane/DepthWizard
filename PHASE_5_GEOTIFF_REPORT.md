# DEPTHWIZARD — PHASE 5: GEOSPATIAL & GEOTIFF PIPELINE REPORT

**Service**: DepthWizard AI Remote-Sensing 3D Reconstruction Platform  
**Pipeline Version**: 1.0.0  
**Phase**: Phase 5 — Geospatial / GeoTIFF Pipeline  
**Date**: September 2026  
**Status**: Complete & Verified (77/77 Unit & Integration Tests Passing)

---

## 1. Executive Summary

Phase 5 implements an exhaustive, mathematically verified, and spatially lossless **GeoTIFF and geospatial raster pipeline** for DepthWizard. The system now provides end-to-end geospatial fidelity, ensuring that remote-sensing imagery ingested as GeoTIFF passes through neural depth estimation, scale calibration, and DSM rasterization while preserving exact coordinate reference systems (CRS), affine geotransforms, spatial extents, pixel resolutions, and NoData masks.

All 10 required test scenarios—including multi-CRS reprojection, sub-pixel raster alignment, multi-band ingestion, NoData masking, and full `read → process → calibrate → DSM → export → reopen` roundtrips—have been validated with 100% test pass rates across the backend test suite.

---

## 2. Input Ingestion & Georeferencing Determination

### 2.1 Supported Raster Formats
- **Standard Optical TIFF**: Single-band or multi-band TIFF lacking spatial tags, correctly classified as `Non-georeferenced optical image (TIFF)`.
- **Geospatial TIFF (GeoTIFF)**: Rasters containing GDAL/GeoTIFF projection tags, affine geotransforms, and coordinate metadata.
- **Consumer Formats**: PNG, JPEG imagery for preview and relative relief reconstructions.

### 2.2 Georeferenced Determination Engine
To eliminate ambiguity, a raster is certified as **actually georeferenced** if and only if all five mathematical conditions are satisfied:
1. **Valid CRS**: `src.crs is not None` and can be instantiated by PROJ without error.
2. **Non-Identity Transform**: `src.transform != Affine.identity()` (identity transform represents unreferenced pixel coordinates).
3. **Non-Degenerate Determinant**: $|\det(\text{transform})| > 10^{-12}$, proving non-zero spatial area per cell.
4. **Strictly Positive Resolution**: $|dx| > 0$ and $|dy| > 0$ with finite values.
5. **Finite, Non-Zero Bounding Coordinates**: Bounding box coordinates $(\text{left}, \text{bottom}, \text{right}, \text{top})$ are finite numbers where $\text{right} > \text{left}$ and $\text{top} > \text{bottom}$.

If any condition fails, the file is safely treated as unreferenced pixel space without crashing or fabricating false geographic coordinates.

### 2.3 Multi-Band & Multi-Dtype Support
Remote sensing imagery arrives across varied band counts and bit depths:
- **1-Band (Panchromatic / Grayscale)**: Replicated to 3-channel RGB: `(H, W, 3)`.
- **2-Band**: Channels mapped to `(B1, B2, B1)` for 3-channel ingestion.
- **3-Band (Standard RGB)**: Extracted directly as `(R, G, B)`.
- **4-Band (RGBA or RGB + NIR)**: Optical bands 1–3 extracted for neural model; alpha/NIR channels recorded in metadata.
- **$\ge$ 5-Band (Multispectral)**: Primary optical bands extracted; total band count tracked.
- **High Dynamic Range (16-bit / 32-bit Float)**: Dynamically normalized to $[0, 255]$ uint8 for neural depth estimation using 2nd–98th percentile scaling while preserving the original spatial metadata and native nodata mask.

### 2.4 Cryptographic Provenance Hashing
Every uploaded raster is hashed using **SHA-256** upon ingestion. The resulting 64-character hexadecimal digest is recorded in `ImageMetadata`, serialized into the project report, and permanently embedded into output GeoTIFF tags.

---

## 3. Coordinate Reference System (CRS) & Alignment Engine

### 3.1 Explicit Reprojection & Resampling
The pipeline never assumes that the primary imagery and reference elevation datasets share identical coordinate systems or resolutions.

When co-registering a reference DEM against primary imagery:
1. **Explicit Reprojection**: Uses `rasterio.warp.reproject` with bilinear interpolation (`Resampling.bilinear`) to reproject from `src.crs` to `target.crs`.
2. **Exact Grid Alignment**: Evaluates elevation values at the exact pixel centers dictated by the primary image's affine transform `target.transform`.
3. **Different Resolution Handling**: Downsamples or upsamples reference DEMs (e.g. 30m SRTM or 0.5m LiDAR) onto the exact pixel spacing $(dx, dy)$ of the optical raster.

### 3.2 Bounding Extent Overlap Verification
To prevent corrupted calibrations when mismatched files are uploaded, `GeospatialService.check_bounds_overlap()` converts both bounding boxes to WGS84 (EPSG:4326) and verifies positive intersection area. If the reference DEM does not spatially cover the primary imagery, a `SpatialOverlapError` is raised immediately, halting processing before bad data can corrupt model outputs.

### 3.3 NoData Preservation & Masking
Source NoData values (e.g. $-9999.0$, $-32767.0$, or $<-9000$) in reference DEMs are converted to `np.nan`. Calibration regressions and statistical metrics automatically ignore invalid/NoData pixels.

---

## 4. DSM Output Specification

The generated DSM GeoTIFF preserves:
- **Coordinate Reference System**: Exact primary CRS preserved (e.g. `EPSG:32643`).
- **Affine Geotransform**: Exact primary 6-parameter affine transform list.
- **Dimensions**: Exact $H \times W$ matching the input raster.
- **Ground Resolution**: Exact ground sampling distance in native map units.
- **NoData Value**: Standardized to `-9999.0`.
- **Data Type**: 32-bit floating point (`float32`).
- **Elevation Units**: `"meters"` for metric calibrated DSM; `"relative"` for rDSM.
- **Spatial Correspondence**: Pixel $(i, j)$ in the output DSM corresponds to the identical geographic point as pixel $(i, j)$ in the input image.

---

## 5. Metadata Provenance & GDAL Tags

Every exported DSM, slope, and hillshade GeoTIFF contains embedded GDAL/TIFF tags for full forensic traceability:

| Tag Name | Description | Example Value |
|:---|:---|:---|
| `INPUT_FILENAME` | Original name of uploaded image | `acceptance_optical.tif` |
| `INPUT_HASH` | SHA-256 hash of input image | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `CRS` | Coordinate reference system | `EPSG:32643` |
| `RESOLUTION` | Cell resolution $(dx, dy)$ | `2.0,2.0` |
| `MODEL` | Neural depth model name | `depth-anything/Depth-Anything-V2-Small-hf` |
| `MODEL_VERSION` | Version of the model | `1.0.0` |
| `CALIBRATION_METHOD` | Scaling strategy used | `dem` |
| `REFERENCE_SOURCE` | Reference dataset used | `acceptance_ref_dem.tif` |
| `ELEVATION_UNITS` | Units of raster values | `meters` |
| `PIPELINE_VERSION` | DepthWizard pipeline release | `1.0.0` |
| `TIMESTAMP` | Processing timestamp (UTC) | `2026-09-09T16:49:08.123456+00:00` |

---

## 6. Export & Roundtrip Verification

The backend provides automated roundtrip verification via `GeospatialService.verify_geotiff_roundtrip()` and endpoint `GET /api/results/{job_id}/verify_geotiff`.

The verification test reopens the written GeoTIFF using GDAL/rasterio and validates:
- **CRS Preserved**: `dst.crs == expected_crs`
- **Transform Preserved**: `dst.transform == expected_transform`
- **Dimensions Preserved**: `dst.width == exp_w` and `dst.height == exp_h`
- **NoData Preserved**: `dst.nodata == -9999.0`
- **Pixel Values Preserved**: $\max(|y_{\text{read}} - y_{\text{expected}}|) < 10^{-4}$ (within float32 precision)
- **Metadata Tags Retrievable**: All GDAL tags present and populated.

---

## 7. Test Suite Execution & Acceptance Matrix

The dedicated Phase 5 test suite ([`test_phase5_geotiff.py`](file:///Users/ojas/Desktop/SIH-2026/DepthWizard-new/backend/tests/test_phase5_geotiff.py)) verifies all requirements:

```bash
PYTHONPATH=backend ./backend/venv/bin/pytest backend/tests/test_phase5_geotiff.py -v
```

### Test Results
| Test ID | Test Scenario | Verified Condition | Status |
|:---|:---|:---|:---:|
| **01** | `test_geotiff_with_crs` | UTM EPSG:32643, bounds, resolution, SHA-256 hash | **PASSED** |
| **02** | `test_geotiff_without_crs` | Unreferenced TIFF marked `is_georeferenced=False` | **PASSED** |
| **03** | `test_different_crs_reference` | Primary UTM 43N reprojects with WGS84 EPSG:4326 DEM | **PASSED** |
| **04** | `test_different_resolution` | 1.0m optical raster aligned with 30.0m DEM | **PASSED** |
| **05** | `test_different_extent_and_non_overlap_rejection` | Overlapping extent clipped; non-overlapping raises `SpatialOverlapError` | **PASSED** |
| **06** | `test_nodata_preservation` | NoData masked to NaN and saved with `nodata=-9999.0` | **PASSED** |
| **07** | `test_invalid_file_rejection` | Corrupted/truncated file cleanly rejected with `ValueError` | **PASSED** |
| **08** | `test_multiband_imagery` | 1-band gray, 3-band RGB, 4-band RGBA, 8-band multispectral, 16-bit | **PASSED** |
| **09** | `test_large_raster_processing` | $1024 \times 1024$ and large rasters processed and exported | **PASSED** |
| **10** | `test_end_to_end_acceptance_roundtrip` | **Full acceptance cycle**: read $\rightarrow$ process $\rightarrow$ calibrate $\rightarrow$ DSM $\rightarrow$ export $\rightarrow$ reopen | **PASSED** |

### Complete Backend Test Suite Status
Across all test modules in the repository:
```
======================= 77 passed, 14 warnings in 21.48s =======================
```
- `test_phase5_geotiff.py`: **10/10 passed**
- `test_gamus_benchmark.py`: **21/21 passed**
- `test_scientific_pipeline.py`: **15/15 passed**
- `test_dataset_workflow.py`: **13/13 passed**
- `test_image_validation.py`: **6/6 passed**
- `test_comprehensive_pipeline.py`: **6/6 passed**
- `test_configurable_metrics.py`: **3/3 passed**
- `test_api.py`: **3/3 passed**

**Zero regressions. Zero hardcoded placeholders. 100% verified.**

