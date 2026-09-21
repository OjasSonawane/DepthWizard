import io
import json
import zipfile
import pytest
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
import rasterio
from rasterio.transform import from_origin

from app.main import app
from app.config import settings

client = TestClient(app)

def create_tiny_image_bytes(w=16, h=10):
    img = Image.new('RGB', (w, h), color=(128, 140, 150))
    # Add a slight diagonal gradient
    pixels = img.load()
    for y in range(h):
        for x in range(w):
            val = int(80 + 100 * (x / max(w-1, 1) + y / max(h-1, 1)) / 2)
            pixels[x, y] = (val, val + 10, val - 10)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

def create_geotiff_bytes(w=64, h=64, crs='EPSG:32643', res=10.0):
    buf = io.BytesIO()
    transform = from_origin(300000.0, 3400000.0, res, res)
    data = np.random.randint(50, 200, (3, h, w), dtype=np.uint8)
    with rasterio.open(
        buf, 'w',
        driver='GTiff',
        height=h,
        width=w,
        count=3,
        dtype='uint8',
        crs=crs,
        transform=transform
    ) as dst:
        dst.write(data)
    buf.seek(0)
    return buf

def create_dem_geotiff_bytes(w=64, h=64, crs='EPSG:32643', res=10.0, base_elev=2000.0):
    buf = io.BytesIO()
    transform = from_origin(300000.0, 3400000.0, res, res)
    y, x = np.mgrid[:h, :w]
    elev = (base_elev + x * 5.0 + y * 8.0).astype(np.float32)
    with rasterio.open(
        buf, 'w',
        driver='GTiff',
        height=h,
        width=w,
        count=1,
        dtype='float32',
        crs=crs,
        transform=transform
    ) as dst:
        dst.write(elev, 1)
    buf.seek(0)
    return buf

# =========================================================================
# TEST CASE A: Tiny 16x10 Input Image (Blockiness & Warning Fix)
# =========================================================================
def test_case_a_tiny_16x10_image():
    # 1. Upload tiny image
    img_buf = create_tiny_image_bytes(16, 10)
    upload_resp = client.post(
        '/api/upload',
        files={'image': ('tiny_16x10.png', img_buf, 'image/png')}
    )
    assert upload_resp.status_code == 200
    upload_data = upload_resp.json()
    job_id = upload_data['job_id']
    meta = upload_data['metadata']

    assert meta['width'] == 16
    assert meta['height'] == 10
    assert meta['is_low_resolution'] is True
    assert 'preview only' in meta['resolution_warning'].lower() or 'preview' in meta['resolution_warning'].lower()

    # 2. Process reconstruction
    proc_resp = client.post(f'/api/process/{job_id}')
    assert proc_resp.status_code == 200
    summary = proc_resp.json()

    # Verify pipeline dimensions are stored and separated
    dims = summary['dimensions']
    assert dims is not None
    assert dims['input_width'] == 16
    assert dims['input_height'] == 10
    assert dims['dsm_width'] == 16
    assert dims['dsm_height'] == 10
    assert dims['render_grid_width'] > 16
    assert dims['is_low_resolution'] is True
    assert dims['interpolation_applied'] is True
    assert dims['interpolation_method'] == 'bicubic'

    # Verify mesh heightfield does not contain blocky NaN/inf and is smooth
    hf_url = summary['assets']['mesh_heightfield']
    hf_resp = client.get(hf_url)
    assert hf_resp.status_code == 200
    hf_data = hf_resp.json()
    assert hf_data['data_width'] == 16
    assert hf_data['data_height'] == 10
    assert hf_data['is_upsampled'] is True

    heights = np.array(hf_data['heights'])
    assert not np.isnan(heights).any()
    assert not np.isinf(heights).any()
    # Check that heights have continuous transitions rather than repeating step plateaus
    grid_w = hf_data['grid_width']
    grid_h = hf_data['grid_height']
    h_2d = heights.reshape(grid_h, grid_w)
    # Differences between neighboring cells should be gradual
    diff_x = np.abs(np.diff(h_2d, axis=1))
    assert np.all(diff_x < 5.0)

# =========================================================================
# TEST CASE B: 512x512 Non-Georeferenced RGB Image (Relative rDSM)
# =========================================================================
def test_case_b_512x512_relative_image():
    load_resp = client.post('/api/samples/aerial_urban_flood/load')
    assert load_resp.status_code == 200
    upload_data = load_resp.json()
    job_id = upload_data['job_id']
    assert upload_data['metadata']['is_georeferenced'] is False
    assert upload_data['metadata']['is_low_resolution'] is False

    proc_resp = client.post(f'/api/process/{job_id}')
    assert proc_resp.status_code == 200
    summary = proc_resp.json()

    assert summary['is_georeferenced'] is False
    assert summary['calibration']['is_metric'] is False
    assert summary['calibration']['method'] == 'relative'
    assert summary['dsm_stats']['is_metric'] is False
    assert 0.0 <= summary['dsm_stats']['min_elevation'] <= 100.0
    assert 0.0 <= summary['dsm_stats']['max_elevation'] <= 100.0

    dims = summary['dimensions']
    assert dims['input_width'] == 512
    assert dims['input_height'] == 512
    assert dims['is_low_resolution'] is False

# =========================================================================
# TEST CASE C: Georeferenced GeoTIFF (CRS & Scaled Estimate Calibration)
# =========================================================================
def test_case_c_georeferenced_geotiff():
    gtiff_buf = create_geotiff_bytes(64, 64, crs='EPSG:32643', res=10.0)
    upload_resp = client.post(
        '/api/upload',
        files={'image': ('scene_32643.tif', gtiff_buf, 'image/tiff')}
    )
    assert upload_resp.status_code == 200
    upload_data = upload_resp.json()
    job_id = upload_data['job_id']
    assert upload_data['metadata']['is_georeferenced'] is True
    assert upload_data['metadata']['crs'] == 'EPSG:32643'
    assert upload_data['metadata']['resolution'] == [10.0, 10.0]

    proc_resp = client.post(f'/api/process/{job_id}')
    assert proc_resp.status_code == 200
    summary = proc_resp.json()

    assert summary['is_georeferenced'] is True
    assert summary['calibration']['method'] == 'scaled_estimate'
    assert summary['calibration']['confidence'] == 'estimated'

    # Check generated GeoTIFF maintains CRS
    dsm_tif_path = settings.DSM_DIR / f'{job_id}_dsm.tif'
    assert dsm_tif_path.exists()
    with rasterio.open(dsm_tif_path) as src:
        assert src.crs is not None
        assert '32643' in str(src.crs)
        assert src.transform is not None

# =========================================================================
# TEST CASE D: Georeferenced GeoTIFF with Reference DEM (Huber Calibration)
# =========================================================================
def test_case_d_dem_huber_calibration():
    load_resp = client.post('/api/samples/himalayan_valley/load')
    assert load_resp.status_code == 200
    upload_data = load_resp.json()
    job_id = upload_data['job_id']
    assert upload_data['has_dem'] is True

    proc_resp = client.post(f'/api/process/{job_id}')
    assert proc_resp.status_code == 200
    summary = proc_resp.json()

    calib = summary['calibration']
    assert calib['method'] == 'dem'
    assert calib['is_metric'] is True
    assert calib['scale'] > 0.0
    assert calib['confidence'] in ['high', 'medium']
    assert calib['r2'] is not None
    assert calib['rmse'] is not None
    assert calib['mae'] is not None
    assert calib['correlation'] is not None
    assert calib['valid_pixels'] > 0

    # Test quantitative evaluation
    ref_dem_file = settings.SAMPLES_DIR / 'himalayan_valley' / 'himalayan_ref_dem.tif'
    with open(ref_dem_file, 'rb') as f:
        eval_resp = client.post(
            f'/api/evaluate/{job_id}',
            files={'reference_file': ('ref_dem.tif', f, 'image/tiff')}
        )
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data['has_evaluation'] is True
    assert eval_data['metrics']['mae'] >= 0.0
    assert eval_data['metrics']['rmse'] >= 0.0
    assert eval_data['metrics']['valid_pixel_pct'] > 90.0
    assert len(eval_data['scatter_samples']) > 0

# =========================================================================
# TEST CASE E: Georeferenced GeoTIFF with GCP CSV (GCP Huber Calibration)
# =========================================================================
def test_case_e_gcp_calibration():
    # Load himalayan valley with its GCPs
    gtiff_file = settings.SAMPLES_DIR / 'himalayan_valley' / 'himalayan_scene.tif'
    gcp_file = settings.SAMPLES_DIR / 'himalayan_valley' / 'himalayan_gcps.csv'

    with open(gtiff_file, 'rb') as f_img, open(gcp_file, 'rb') as f_gcp:
        upload_resp = client.post(
            '/api/upload',
            files={
                'image': ('himalayan_scene.tif', f_img, 'image/tiff'),
                'gcp': ('himalayan_gcps.csv', f_gcp, 'text/csv')
            }
        )
    assert upload_resp.status_code == 200
    upload_data = upload_resp.json()
    job_id = upload_data['job_id']
    assert upload_data['has_gcp'] is True
    assert len(upload_data['parsed_gcps']) == 6

    proc_resp = client.post(f'/api/process/{job_id}')
    assert proc_resp.status_code == 200
    summary = proc_resp.json()

    calib = summary['calibration']
    assert calib['method'] == 'gcp'
    assert calib['is_metric'] is True
    assert calib['gcp_count'] == 6
    assert calib['rmse'] is not None

# =========================================================================
# TEST CASE F: Export Archive Integrity & Metadata Report
# =========================================================================
def test_case_f_export_archive():
    load_resp = client.post('/api/samples/coastal_estuary/load')
    job_id = load_resp.json()['job_id']
    client.post(f'/api/process/{job_id}')

    # Download export ZIP
    export_resp = client.get(f'/api/results/{job_id}/export')
    assert export_resp.status_code == 200
    assert export_resp.headers['content-type'] == 'application/zip'

    # Inspect zip contents
    zip_bytes = io.BytesIO(export_resp.content)
    with zipfile.ZipFile(zip_bytes, 'r') as zf:
        namelist = zf.namelist()
        assert any(n.startswith('dsm/') and n.endswith('_dsm.tif') for n in namelist)
        assert any(n.startswith('dsm/') and n.endswith('_slope.tif') for n in namelist)
        assert any(n.startswith('dsm/') and n.endswith('_hillshade.tif') for n in namelist)
        assert any(n.startswith('mesh/') and n.endswith('_terrain.obj') for n in namelist)
        assert any(n.startswith('mesh/') and n.endswith('_heightfield.json') for n in namelist)
        assert 'project_report.json' in namelist

        # Validate project report JSON contains pipeline_dimensions
        report_data = json.loads(zf.read('project_report.json').decode('utf-8'))
        assert 'pipeline_dimensions' in report_data
        assert 'dsm_statistics' in report_data
        assert report_data['input']['is_georeferenced'] is True
