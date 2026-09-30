import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "DepthWizard"
    assert "device" in data

def test_samples_catalog():
    response = client.get("/api/samples")
    assert response.status_code == 200
    samples = response.json()
    assert len(samples) >= 3
    ids = [s["id"] for s in samples]
    assert "himalayan_valley" in ids
    assert "coastal_estuary" in ids
    assert "aerial_urban_flood" in ids

def test_load_sample_and_pipeline():
    # 1. Load sample dataset
    load_resp = client.post("/api/samples/himalayan_valley/load")
    assert load_resp.status_code == 200
    job_info = load_resp.json()
    job_id = job_info["job_id"]
    assert job_info["metadata"]["is_georeferenced"] is True
    assert job_info["metadata"]["crs"] == "EPSG:32643"
    assert job_info["has_dem"] is True

    # 2. Check initial status
    status_resp = client.get(f"/api/jobs/{job_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["job_id"] == job_id

    # 3. Process job
    proc_resp = client.post(f"/api/process/{job_id}")
    assert proc_resp.status_code == 200
    summary = proc_resp.json()
    assert summary["job_id"] == job_id
    assert summary["is_georeferenced"] is True
    assert summary["calibration"]["is_metric"] is True
    assert summary["dsm_stats"]["max_elevation"] > summary["dsm_stats"]["min_elevation"]
    assert summary["mesh_metadata"]["vertex_count"] > 0
    assert "rgb_texture" in summary["assets"]
    assert "mesh_heightfield" in summary["assets"]

    # 4. Results endpoints
    res_resp = client.get(f"/api/results/{job_id}")
    assert res_resp.status_code == 200

    depth_resp = client.get(f"/api/results/{job_id}/depth")
    assert depth_resp.status_code == 200
    assert "depth_color" in depth_resp.json()

    dsm_resp = client.get(f"/api/results/{job_id}/dsm")
    assert dsm_resp.status_code == 200
    assert dsm_resp.json()["is_metric"] is True

    # 5. Analysis: Terrain Profile
    prof_resp = client.post(f"/api/analysis/profile/{job_id}", json={
        "x1_pct": 0.1, "y1_pct": 0.1,
        "x2_pct": 0.9, "y2_pct": 0.9,
        "samples": 50
    })
    assert prof_resp.status_code == 200
    prof_data = prof_resp.json()
    assert len(prof_data["points"]) == 50
    assert prof_data["total_distance_m"] > 0

    # 6. Analysis: Flood simulation
    mid_elev = summary["dsm_stats"]["median_elevation"]
    flood_resp = client.post(f"/api/analysis/flood/{job_id}", json={
        "water_elevation": mid_elev
    })
    assert flood_resp.status_code == 200
    flood_data = flood_resp.json()
    assert 0.0 <= flood_data["inundated_area_pct"] <= 100.0

    # 7. Evaluation against reference DEM
    ref_dem_file = settings.SAMPLES_DIR / "himalayan_valley" / "himalayan_ref_dem.tif"
    with open(ref_dem_file, "rb") as f:
        eval_resp = client.post(
            f"/api/evaluate/{job_id}",
            files={"reference_file": ("ref.tif", f, "image/tiff")}
        )
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["has_evaluation"] is True
    assert eval_data["metrics"]["mae"] >= 0.0
    assert eval_data["metrics"]["rmse"] >= 0.0
    assert -1.0 <= eval_data["metrics"]["pearson_r"] <= 1.0
    assert len(eval_data["error_histogram"]) > 0

    # 8. Export archive
    export_resp = client.get(f"/api/results/{job_id}/export")
    assert export_resp.status_code == 200
    assert export_resp.headers["content-type"] == "application/zip"
