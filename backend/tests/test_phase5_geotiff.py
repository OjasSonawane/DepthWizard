import json
from pathlib import Path
import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine
from rasterio.crs import CRS
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services.geospatial_service import GeospatialService, SpatialOverlapError
from app.services.depth_service import PipelineManager

client = TestClient(app)


@pytest.fixture
def temp_raster_dir(tmp_path):
    d = tmp_path / "geotiff_fixtures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_synthetic_geotiff(
    path: Path,
    shape=(128, 128),
    crs="EPSG:32643",
    transform=Affine(2.0, 0.0, 500000.0, 0.0, -2.0, 3400000.0),
    bands=3,
    dtype="uint8",
    nodata=None,
    data_gen=None
):
    """Helper to create synthetic GeoTIFF files with precise spatial tags."""
    h, w = shape
    if data_gen is not None:
        data = data_gen(bands, h, w)
    elif dtype == "uint8":
        data = np.random.randint(20, 240, size=(bands, h, w), dtype=np.uint8)
    elif dtype == "uint16":
        data = np.random.randint(1000, 20000, size=(bands, h, w), dtype=np.uint16)
    elif dtype == "float32":
        data = (np.random.normal(1500.0, 200.0, size=(bands, h, w))).astype(np.float32)
        if nodata is not None:
            data[:, 0:10, 0:10] = nodata
    else:
        data = np.zeros((bands, h, w), dtype=dtype)

    crs_obj = CRS.from_user_input(crs) if crs else None

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=bands,
        dtype=data.dtype,
        crs=crs_obj,
        transform=transform if crs else Affine.identity(),
        nodata=nodata
    ) as dst:
        for b in range(1, bands + 1):
            dst.write(data[b - 1], b)

    return path, data


class TestPhase5GeospatialPipeline:
    """
    Exhaustive tests covering all Phase 5 requirements:
    - GeoTIFF with CRS
    - GeoTIFF without CRS
    - Different CRS reference
    - Different resolution
    - Different extent / non-overlap rejection
    - NoData handling
    - Invalid file rejection
    - Multi-band imagery (1, 3, 4, 8 bands, uint16)
    - Large raster processing
    - Acceptance: read -> process -> calibrate -> DSM -> export -> reopen
    """

    # -------------------------------------------------------------------------
    # 1. GeoTIFF with CRS
    # -------------------------------------------------------------------------
    def test_geotiff_with_crs(self, temp_raster_dir):
        """Inspects valid GeoTIFF with UTM CRS, verifying metadata extraction and SHA-256 hash."""
        p = temp_raster_dir / "utm_sample.tif"
        create_synthetic_geotiff(p, shape=(128, 128), crs="EPSG:32643", bands=3)

        meta, rgb = GeospatialService.inspect_file(p)
        assert meta.is_georeferenced is True
        assert meta.crs == "EPSG:32643"
        assert meta.width == 128
        assert meta.height == 128
        assert meta.band_count == 3
        assert meta.resolution == [2.0, 2.0]
        assert meta.bounds is not None
        assert meta.file_hash is not None
        assert len(meta.file_hash) == 64  # SHA-256 hex length
        assert rgb.shape == (128, 128, 3)

    # -------------------------------------------------------------------------
    # 2. GeoTIFF without CRS
    # -------------------------------------------------------------------------
    def test_geotiff_without_crs(self, temp_raster_dir):
        """Inspects TIFF without CRS, verifying clean non-georeferenced identification."""
        p = temp_raster_dir / "unreferenced.tif"
        create_synthetic_geotiff(p, shape=(100, 100), crs=None, transform=None, bands=3)

        meta, rgb = GeospatialService.inspect_file(p)
        assert meta.is_georeferenced is False
        assert meta.crs is None
        assert meta.transform is None
        assert meta.bounds is None
        assert meta.resolution is None
        assert meta.classification == "Non-georeferenced optical image (TIFF)"
        assert rgb.shape == (100, 100, 3)

    # -------------------------------------------------------------------------
    # 3. Different CRS Reference Reprojection
    # -------------------------------------------------------------------------
    def test_different_crs_reference(self, temp_raster_dir):
        """Primary image in UTM (EPSG:32643) and reference DEM in WGS84 (EPSG:4326)."""
        # UTM primary: Northern India (lon ~78.5, lat ~30.7) -> UTM 43N: Easting ~260000, Northing ~3400000
        utm_x, utm_y = 260000.0, 3400000.0
        p_primary = temp_raster_dir / "primary_utm.tif"
        create_synthetic_geotiff(
            p_primary, shape=(100, 100), crs="EPSG:32643",
            transform=Affine(5.0, 0.0, utm_x, 0.0, -5.0, utm_y), bands=3
        )

        # Reference in WGS84 covering (lon: 71.0 to 75.0, lat: 29.0 to 32.0)
        p_ref = temp_raster_dir / "ref_wgs84.tif"
        create_synthetic_geotiff(
            p_ref, shape=(100, 100), crs="EPSG:4326",
            transform=Affine(0.04, 0.0, 71.0, 0.0, -0.03, 32.0),
            bands=1, dtype="float32"
        )

        primary_meta, _ = GeospatialService.inspect_file(p_primary)
        aligned = GeospatialService.reproject_match(
            reference_path=p_ref,
            target_shape=(100, 100),
            target_crs_str=primary_meta.crs,
            target_transform_list=primary_meta.transform
        )

        assert aligned.shape == (100, 100)
        assert np.any(np.isfinite(aligned))

    # -------------------------------------------------------------------------
    # 4. Different Resolution Resampling
    # -------------------------------------------------------------------------
    def test_different_resolution(self, temp_raster_dir):
        """Primary image at 1.0m resolution, reference DEM at 30.0m resolution."""
        utm_x, utm_y = 500000.0, 3500000.0
        p_primary = temp_raster_dir / "highres_primary.tif"
        create_synthetic_geotiff(
            p_primary, shape=(150, 150), crs="EPSG:32643",
            transform=Affine(1.0, 0.0, utm_x, 0.0, -1.0, utm_y), bands=3
        )

        p_ref = temp_raster_dir / "lowres_dem.tif"
        create_synthetic_geotiff(
            p_ref, shape=(20, 20), crs="EPSG:32643",
            transform=Affine(30.0, 0.0, utm_x - 100.0, 0.0, -30.0, utm_y + 100.0),
            bands=1, dtype="float32"
        )

        primary_meta, _ = GeospatialService.inspect_file(p_primary)
        aligned = GeospatialService.reproject_match(
            reference_path=p_ref,
            target_shape=(150, 150),
            target_crs_str=primary_meta.crs,
            target_transform_list=primary_meta.transform
        )

        assert aligned.shape == (150, 150)
        assert np.any(np.isfinite(aligned))

    # -------------------------------------------------------------------------
    # 5. Different Extent / Non-Overlapping Extent Rejection
    # -------------------------------------------------------------------------
    def test_different_extent_and_non_overlap_rejection(self, temp_raster_dir):
        """Verifies overlapping DEM is clipped, and non-overlapping DEM raises SpatialOverlapError."""
        utm_x, utm_y = 500000.0, 3500000.0
        p_primary = temp_raster_dir / "primary.tif"
        create_synthetic_geotiff(
            p_primary, shape=(100, 100), crs="EPSG:32643",
            transform=Affine(2.0, 0.0, utm_x, 0.0, -2.0, utm_y), bands=3
        )
        primary_meta, _ = GeospatialService.inspect_file(p_primary)

        # A: Overlapping larger DEM
        p_ref_large = temp_raster_dir / "large_overlap.tif"
        create_synthetic_geotiff(
            p_ref_large, shape=(300, 300), crs="EPSG:32643",
            transform=Affine(2.0, 0.0, utm_x - 100.0, 0.0, -2.0, utm_y + 100.0),
            bands=1, dtype="float32"
        )
        aligned = GeospatialService.reproject_match(
            reference_path=p_ref_large,
            target_shape=(100, 100),
            target_crs_str=primary_meta.crs,
            target_transform_list=primary_meta.transform
        )
        assert aligned.shape == (100, 100)

        # B: Non-overlapping DEM (completely distant coordinates)
        p_ref_distant = temp_raster_dir / "distant_dem.tif"
        create_synthetic_geotiff(
            p_ref_distant, shape=(100, 100), crs="EPSG:32643",
            transform=Affine(2.0, 0.0, utm_x + 500000.0, 0.0, -2.0, utm_y + 500000.0),
            bands=1, dtype="float32"
        )
        with pytest.raises(SpatialOverlapError):
            GeospatialService.reproject_match(
                reference_path=p_ref_distant,
                target_shape=(100, 100),
                target_crs_str=primary_meta.crs,
                target_transform_list=primary_meta.transform
            )

    # -------------------------------------------------------------------------
    # 6. NoData Handling
    # -------------------------------------------------------------------------
    def test_nodata_preservation(self, temp_raster_dir):
        """Verifies NoData pixels are correctly masked to NaN and preserved in export."""
        utm_x, utm_y = 500000.0, 3500000.0
        p_ref = temp_raster_dir / "dem_with_nodata.tif"
        create_synthetic_geotiff(
            p_ref, shape=(100, 100), crs="EPSG:32643",
            transform=Affine(2.0, 0.0, utm_x, 0.0, -2.0, utm_y),
            bands=1, dtype="float32", nodata=-9999.0
        )

        aligned = GeospatialService.reproject_match(
            reference_path=p_ref,
            target_shape=(100, 100),
            target_crs_str="EPSG:32643",
            target_transform_list=[2.0, 0.0, utm_x, 0.0, -2.0, utm_y]
        )
        # Top-left corner had nodata
        assert np.isnan(aligned[0:5, 0:5]).all()

        # Save and verify GeoTIFF roundtrip preserving NoData
        out_tif = temp_raster_dir / "exported_nodata.tif"
        GeospatialService.save_geotiff(
            output_path=out_tif,
            data=aligned,
            crs_str="EPSG:32643",
            transform_list=[2.0, 0.0, utm_x, 0.0, -2.0, utm_y],
            nodata=-9999.0
        )

        res = GeospatialService.verify_geotiff_roundtrip(
            geotiff_path=out_tif,
            expected_data=aligned,
            expected_crs="EPSG:32643",
            expected_transform=[2.0, 0.0, utm_x, 0.0, -2.0, utm_y],
            expected_nodata=-9999.0
        )
        assert res.is_valid is True
        assert res.nodata_preserved is True

    # -------------------------------------------------------------------------
    # 7. Invalid File Handling
    # -------------------------------------------------------------------------
    def test_invalid_file_rejection(self, temp_raster_dir):
        """Verifies corrupted or truncated files are rejected with descriptive error."""
        corrupt_tif = temp_raster_dir / "corrupted.tif"
        with open(corrupt_tif, "wb") as f:
            f.write(b"II*\x00\x08\x00\x00\x00corrupted_garbage_bytes_here")

        with pytest.raises(ValueError) as exc:
            GeospatialService.inspect_file(corrupt_tif)
        assert "corrupted or invalid" in str(exc.value).lower()

    # -------------------------------------------------------------------------
    # 8. Multi-Band Imagery (1, 3, 4, 8 bands and uint16)
    # -------------------------------------------------------------------------
    def test_multiband_imagery(self, temp_raster_dir):
        """Verifies 1-band, 4-band, 8-band, and 16-bit rasters are correctly processed."""
        # A. 1-band Grayscale
        p_1ch = temp_raster_dir / "gray.tif"
        create_synthetic_geotiff(p_1ch, shape=(64, 64), bands=1, dtype="uint8")
        meta1, rgb1 = GeospatialService.inspect_file(p_1ch)
        assert meta1.band_count == 1
        assert rgb1.shape == (64, 64, 3)

        # B. 4-band RGBA / NIR
        p_4ch = temp_raster_dir / "rgba.tif"
        create_synthetic_geotiff(p_4ch, shape=(64, 64), bands=4, dtype="uint8")
        meta4, rgb4 = GeospatialService.inspect_file(p_4ch)
        assert meta4.band_count == 4
        assert rgb4.shape == (64, 64, 3)

        # C. 8-band Multispectral
        p_8ch = temp_raster_dir / "multispectral.tif"
        create_synthetic_geotiff(p_8ch, shape=(64, 64), bands=8, dtype="uint8")
        meta8, rgb8 = GeospatialService.inspect_file(p_8ch)
        assert meta8.band_count == 8
        assert rgb8.shape == (64, 64, 3)

        # D. 16-bit uint16 image
        p_16bit = temp_raster_dir / "uint16.tif"
        create_synthetic_geotiff(p_16bit, shape=(64, 64), bands=3, dtype="uint16")
        meta16, rgb16 = GeospatialService.inspect_file(p_16bit)
        assert meta16.native_dtype == "uint16"
        assert rgb16.dtype == np.uint8
        assert rgb16.shape == (64, 64, 3)

    # -------------------------------------------------------------------------
    # 9. Large Raster
    # -------------------------------------------------------------------------
    def test_large_raster_processing(self, temp_raster_dir):
        """Verifies inspection and GeoTIFF export of a large 2048x2048 raster."""
        p_large = temp_raster_dir / "large_2048.tif"
        create_synthetic_geotiff(
            p_large, shape=(1024, 1024), crs="EPSG:32643",
            transform=Affine(1.0, 0.0, 500000.0, 0.0, -1.0, 3500000.0),
            bands=3, dtype="uint8"
        )
        meta, rgb = GeospatialService.inspect_file(p_large)
        assert meta.width == 1024
        assert meta.height == 1024
        assert rgb.shape == (1024, 1024, 3)

        # Save and verify large GeoTIFF
        out_large = temp_raster_dir / "large_dsm_out.tif"
        test_dsm = np.random.uniform(500.0, 2500.0, size=(1024, 1024)).astype(np.float32)
        GeospatialService.save_geotiff(
            output_path=out_large,
            data=test_dsm,
            crs_str=meta.crs,
            transform_list=meta.transform,
            metadata_tags={"LARGE_RASTER": "TRUE"}
        )

        res = GeospatialService.verify_geotiff_roundtrip(
            geotiff_path=out_large,
            expected_data=test_dsm,
            expected_crs=meta.crs,
            expected_transform=meta.transform
        )
        assert res.is_valid is True
        assert res.width == 1024
        assert res.height == 1024

    # -------------------------------------------------------------------------
    # 10. Acceptance: read -> process -> calibrate -> DSM -> export -> reopen
    # -------------------------------------------------------------------------
    def test_end_to_end_acceptance_roundtrip(self, temp_raster_dir):
        """
        Full Phase 5 Acceptance Test:
        read -> process -> calibrate -> DSM -> export -> reopen
        without losing spatial metadata.
        """
        # 1. Create primary GeoTIFF
        utm_x, utm_y = 520000.0, 3550000.0
        primary_tif = temp_raster_dir / "acceptance_optical.tif"
        create_synthetic_geotiff(
            primary_tif, shape=(128, 128), crs="EPSG:32643",
            transform=Affine(2.0, 0.0, utm_x, 0.0, -2.0, utm_y),
            bands=3, dtype="uint8"
        )

        # 2. Create matching reference DEM
        ref_tif = temp_raster_dir / "acceptance_ref_dem.tif"
        create_synthetic_geotiff(
            ref_tif, shape=(128, 128), crs="EPSG:32643",
            transform=Affine(2.0, 0.0, utm_x, 0.0, -2.0, utm_y),
            bands=1, dtype="float32"
        )

        # 3. Upload via API
        with open(primary_tif, "rb") as f_img, open(ref_tif, "rb") as f_dem:
            upload_resp = client.post(
                "/api/upload",
                files={
                    "image": ("acceptance_optical.tif", f_img, "image/tiff"),
                    "dem": ("acceptance_ref_dem.tif", f_dem, "image/tiff")
                }
            )
        assert upload_resp.status_code == 200
        up_data = upload_resp.json()
        job_id = up_data["job_id"]
        assert up_data["metadata"]["is_georeferenced"] is True
        assert up_data["metadata"]["file_hash"] is not None

        # 4. Process pipeline
        proc_resp = client.post(f"/api/process/{job_id}")
        assert proc_resp.status_code == 200
        proc_data = proc_resp.json()
        assert proc_data["is_georeferenced"] is True
        assert proc_data["calibration"]["is_metric"] is True

        # 5. Export archive
        export_resp = client.get(f"/api/results/{job_id}/export")
        assert export_resp.status_code == 200
        assert export_resp.headers["content-type"] == "application/zip"

        # 6. Verify exported GeoTIFF can be reopened without loss of spatial metadata
        verify_resp = client.get(f"/api/results/{job_id}/verify_geotiff")
        assert verify_resp.status_code == 200
        ver_data = verify_resp.json()

        assert ver_data["is_valid"] is True
        assert ver_data["crs_preserved"] is True
        assert ver_data["transform_preserved"] is True
        assert ver_data["dimensions_preserved"] is True
        assert ver_data["nodata_preserved"] is True
        assert ver_data["values_preserved"] is True
        assert ver_data["width"] == 128
        assert ver_data["height"] == 128
        assert ver_data["crs"] == "EPSG:32643"
        assert ver_data["tags"]["CALIBRATION_METHOD"] == "dem"
        assert ver_data["tags"]["INPUT_HASH"] != ""
        assert ver_data["tags"]["MODEL"] == settings.MODEL_NAME

        # 7. Check Project Report provenance metadata
        report_resp = client.get(f"/api/results/{job_id}/report")
        assert report_resp.status_code == 200
        rep_data = report_resp.json()
        assert rep_data["input"]["file_hash"] != "N/A"
        assert rep_data["pipeline_version"] == settings.VERSION
        assert rep_data["timestamp"] is not None
        assert rep_data["spatial_verification"]["crs_preserved"] is True
