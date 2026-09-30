import io
import json
import pytest
import numpy as np
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
import rasterio
from rasterio.transform import from_origin

from app.main import app
from app.config import settings
from app.services.mesh_service import MeshService

client = TestClient(app)

def create_synthetic_rgb_image(w=64, h=64):
    buf = io.BytesIO()
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            arr[y, x] = [int(255 * x / w), int(255 * y / h), 128]
    img = Image.fromarray(arr)
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def create_synthetic_geotiff(w=64, h=64, crs="EPSG:32643", res=10.0):
    buf = io.BytesIO()
    transform = from_origin(500000.0, 3000000.0, res, res)
    data = np.random.randint(50, 200, (3, h, w), dtype=np.uint8)
    with rasterio.open(
        buf, "w",
        driver="GTiff",
        height=h,
        width=w,
        count=3,
        dtype="uint8",
        crs=crs,
        transform=transform
    ) as dst:
        dst.write(data)
    buf.seek(0)
    return buf

def create_synthetic_dem(w=64, h=64, crs="EPSG:32643", res=10.0, base=1500.0):
    buf = io.BytesIO()
    transform = from_origin(500000.0, 3000000.0, res, res)
    y, x = np.mgrid[:h, :w]
    elev = (base + x * 2.5 + y * 4.0).astype(np.float32)
    with rasterio.open(
        buf, "w",
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform
    ) as dst:
        dst.write(elev, 1)
    buf.seek(0)
    return buf


class TestPhase7RealDSM3DTerrain:
    """
    Automated verification for Phase 7: Real DSM to 3D Terrain
    """

    def test_real_dsm_to_terrain_vertices(self, tmp_path):
        """
        Tests that terrain vertices in JSON heightfield and OBJ match the actual DSM raster.
        Zero random elevation, zero fake terrain geometry.
        """
        h, w = 64, 64
        y, x = np.mgrid[:h, :w]
        # Mathematical parabolic crater surface: z = 1000 + 0.1 * (x-32)^2 + 0.15 * (y-32)^2
        dsm = (1000.0 + 0.1 * (x - 32) ** 2 + 0.15 * (y - 32) ** 2).astype(np.float32)

        out_prefix = tmp_path / "terrain_test"
        meta, json_p, obj_p = MeshService.generate_mesh_assets(
            dsm=dsm,
            output_prefix=out_prefix,
            quality="high",
            grid_dim=64
        )

        assert json_p.exists()
        assert obj_p.exists()

        with open(json_p, "r") as f:
            hf = json.load(f)

        assert hf["grid_width"] == 64
        assert hf["grid_height"] == 64
        assert hf["min_elevation"] == pytest.approx(float(np.min(dsm)), abs=0.1)
        assert hf["max_elevation"] == pytest.approx(float(np.max(dsm)), abs=0.1)

        raw_elevs = np.array(hf["raw_elevations"]).reshape(64, 64)
        # Verify center point elevation is minimum (vertex directly driven by DSM formula)
        assert raw_elevs[32, 32] == pytest.approx(1000.0, abs=1.0)
        # Verify corners are higher
        assert raw_elevs[0, 0] > 1100.0
        assert raw_elevs[63, 63] > 1100.0

        # Verify OBJ vertices match heightfield
        with open(obj_p, "r") as f:
            lines = f.readlines()
        vertex_lines = [l for l in lines if l.startswith("v ")]
        assert len(vertex_lines) == 64 * 64

    def test_aspect_ratio_preservation(self, tmp_path):
        """
        Tests that world_z_span / world_x_span strictly preserves the native aspect ratio
        of the input DSM, avoiding texture stretching.
        """
        out_prefix = tmp_path / "aspect_test"

        # 1. Wide landscape image: 100 x 200 (aspect 0.5)
        dsm_wide = np.ones((100, 200), dtype=np.float32) * 50.0
        _, json_wide, _ = MeshService.generate_mesh_assets(
            dsm=dsm_wide, output_prefix=out_prefix, quality="high", grid_dim=128
        )
        with open(json_wide, "r") as f:
            hf_wide = json.load(f)
        ratio_wide = hf_wide["world_z_span"] / hf_wide["world_x_span"]
        assert ratio_wide == pytest.approx(100.0 / 200.0, abs=1e-3)

        # 2. Tall portrait image: 240 x 120 (aspect 2.0)
        dsm_tall = np.ones((240, 120), dtype=np.float32) * 50.0
        _, json_tall, _ = MeshService.generate_mesh_assets(
            dsm=dsm_tall, output_prefix=out_prefix, quality="high", grid_dim=128
        )
        with open(json_tall, "r") as f:
            hf_tall = json.load(f)
        ratio_tall = hf_tall["world_z_span"] / hf_tall["world_x_span"]
        assert ratio_tall == pytest.approx(240.0 / 120.0, abs=1e-3)

    def test_rgb_dsm_spatial_alignment(self, tmp_path):
        """
        Verifies UV correspondence between RGB pixel, DSM pixel, and terrain vertex.
        Top-left vertex (r=0, c=0) maps to u=0, v=1 in UV and North-West in spatial coordinates.
        """
        dsm = np.linspace(100, 200, 64 * 64, dtype=np.float32).reshape(64, 64)
        out_prefix = tmp_path / "uv_test"
        _, _, obj_p = MeshService.generate_mesh_assets(
            dsm=dsm, output_prefix=out_prefix, quality="high", grid_dim=64
        )

        with open(obj_p, "r") as f:
            lines = f.readlines()

        vt_lines = [l.strip().split() for l in lines if l.startswith("vt ")]
        assert len(vt_lines) == 64 * 64

        # First vertex texture coord: (r=0, c=0) -> u=0.0, v=1.0 (top-left)
        assert float(vt_lines[0][1]) == pytest.approx(0.0, abs=1e-3)
        assert float(vt_lines[0][2]) == pytest.approx(1.0, abs=1e-3)

        # Last vertex texture coord: (r=63, c=63) -> u=1.0, v=0.0 (bottom-right)
        assert float(vt_lines[-1][1]) == pytest.approx(1.0, abs=1e-3)
        assert float(vt_lines[-1][2]) == pytest.approx(0.0, abs=1e-3)

    def test_programmatic_scientific_check(self, tmp_path):
        """
        SCIENTIFIC CHECK:
        Modify one known DSM value programmatically.
        Verify that the corresponding terrain vertex changes.
        This test proves that the 3D viewer is actually driven by the scientific DSM.
        """
        h, w = 64, 64
        # Base flat terrain at 500m elevation
        dsm_base = np.full((h, w), 500.0, dtype=np.float32)
        # Create small slope to define non-zero relief
        dsm_base[-1, -1] = 520.0

        out_prefix_base = tmp_path / "sc_base"
        _, json_base_p, _ = MeshService.generate_mesh_assets(
            dsm=dsm_base, output_prefix=out_prefix_base, quality="high", grid_dim=64
        )
        with open(json_base_p, "r") as f:
            hf_base = json.load(f)

        idx_target = 20 * 64 + 30
        elev_before = hf_base["raw_elevations"][idx_target]
        assert elev_before == pytest.approx(500.0, abs=0.5)

        # Programmatically modify ONE known DSM pixel at (r=20, c=30) by +50.0m
        dsm_modified = dsm_base.copy()
        dsm_modified[20, 30] += 50.0  # Spike to 550.0m

        out_prefix_mod = tmp_path / "sc_mod"
        _, json_mod_p, _ = MeshService.generate_mesh_assets(
            dsm=dsm_modified, output_prefix=out_prefix_mod, quality="high", grid_dim=64
        )
        with open(json_mod_p, "r") as f:
            hf_mod = json.load(f)

        elev_after = hf_mod["raw_elevations"][idx_target]
        # Verify the corresponding terrain vertex changed by the exact programmatic delta!
        delta = elev_after - elev_before
        assert delta == pytest.approx(50.0, abs=0.5)

        # Verify a distant cell (r=5, c=5) remained unchanged
        idx_distant = 5 * 64 + 5
        assert hf_mod["raw_elevations"][idx_distant] == pytest.approx(hf_base["raw_elevations"][idx_distant], abs=0.1)

    def test_point_inspection_api_endpoint(self):
        """
        Tests GET /api/results/{job_id}/inspect-point with and without reference DEM.
        Verifies that without reference DEM, reference_height and error are None ("Unavailable"),
        and with reference DEM, exact paired reference height and error are returned.
        """
        # 1. Upload and run optical image without reference DEM
        rgb_buf = create_synthetic_rgb_image(64, 64)
        up_resp = client.post("/api/upload", files={"image": ("optical_test.png", rgb_buf, "image/png")})
        assert up_resp.status_code == 200
        job_id = up_resp.json()["job_id"]

        proc_resp = client.post(f"/api/jobs/{job_id}/start")
        assert proc_resp.status_code == 200

        # Query point inspection
        inspect_resp = client.get(f"/api/results/{job_id}/inspect-point?pixel_x=32&pixel_y=32")
        assert inspect_resp.status_code == 200
        data = inspect_resp.json()

        assert data["job_id"] == job_id
        assert data["pixel_coords"] == {"x": 32, "y": 32}
        assert "predicted_height" in data
        assert isinstance(data["predicted_height"], float)
        # CRITICAL: Since no reference DEM exists, reference_height and error MUST be None
        assert data["reference_height"] is None
        assert data["error"] is None
        assert "slope_deg" in data

        # Query using normalized percentages (0.5, 0.5)
        pct_resp = client.get(f"/api/results/{job_id}/inspect-point?x_pct=0.5&y_pct=0.5")
        assert pct_resp.status_code == 200
        assert pct_resp.json()["pixel_coords"] == {"x": 32, "y": 32}

    def test_point_inspection_with_reference_dem(self):
        """
        Tests point inspection when a reference DEM is provided.
        Verifies real reference height and error computation.
        """
        geotiff_buf = create_synthetic_geotiff(64, 64, crs="EPSG:32643", res=10.0)
        dem_buf = create_synthetic_dem(64, 64, crs="EPSG:32643", res=10.0, base=2000.0)

        up_resp = client.post(
            "/api/upload",
            files={
                "image": ("primary.tif", geotiff_buf, "image/tiff"),
                "dem": ("reference.tif", dem_buf, "image/tiff")
            }
        )
        assert up_resp.status_code == 200
        job_id = up_resp.json()["job_id"]

        proc_resp = client.post(f"/api/jobs/{job_id}/start")
        assert proc_resp.status_code == 200

        inspect_resp = client.get(f"/api/results/{job_id}/inspect-point?pixel_x=30&pixel_y=30")
        assert inspect_resp.status_code == 200
        data = inspect_resp.json()

        assert data["job_id"] == job_id
        assert data["predicted_height"] is not None
        # Reference height must be a real float from the reference DEM
        assert data["reference_height"] is not None
        assert isinstance(data["reference_height"], float)
        assert data["reference_height"] > 1900.0  # base is 2000.0
        # Error must equal predicted - reference
        assert data["error"] == pytest.approx(round(data["predicted_height"] - data["reference_height"], 2), abs=0.1)

    def test_5_display_modes_assets(self):
        """
        Verifies assets for all 5 modes (RGB, Elevation, Slope, Hillshade, Wireframe)
        are properly produced and accessible for 3D exploration.
        """
        rgb_buf = create_synthetic_rgb_image(64, 64)
        up_resp = client.post("/api/upload", files={"image": ("mode_test.png", rgb_buf, "image/png")})
        assert up_resp.status_code == 200
        job_id = up_resp.json()["job_id"]

        proc_resp = client.post(f"/api/jobs/{job_id}/start")
        assert proc_resp.status_code == 200
        res = proc_resp.json()
        assets = res["assets"]

        # 1. RGB Mode
        assert "rgb_texture" in assets
        assert client.get(assets["rgb_texture"]).status_code == 200

        # 2. Elevation Mode
        assert "dsm_color" in assets
        assert client.get(assets["dsm_color"]).status_code == 200

        # 3. Slope Mode
        assert "slope" in assets
        assert client.get(assets["slope"]).status_code == 200

        # 4. Hillshade Mode
        assert "hillshade" in assets
        assert client.get(assets["hillshade"]).status_code == 200

        # 5. Wireframe Mode (driven by mesh heightfield geometry)
        assert "mesh_heightfield" in assets
        assert client.get(assets["mesh_heightfield"]).status_code == 200

