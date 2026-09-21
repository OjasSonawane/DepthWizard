# DepthWizard REST API Reference

All API routes are prefixed under `/api`.

---

### 1. System Health
- **Endpoint**: `GET /api/health`
- **Description**: Probes service status, device hardware acceleration, and depth model readiness.
- **Response**:
```json
{
  "status": "healthy",
  "service": "DepthWizard",
  "version": "1.0.0",
  "device": "MPS",
  "model_loaded": true,
  "is_fallback_mode": false,
  "storage_dir": "/path/to/storage"
}
```

---

### 2. File Upload & Inspection
- **Endpoint**: `POST /api/upload`
- **Content-Type**: `multipart/form-data`
- **Form Fields**:
  - `image` (required): Satellite or aerial imagery file (`.tif`, `.tiff`, `.png`, `.jpg`, `.jpeg`).
  - `dem` (optional): Reference DEM GeoTIFF (`.tif`, `.tiff`).
  - `gcp` (optional): Ground Control Points CSV (`.csv`).
- **Response**: `UploadResponse`
```json
{
  "job_id": "dw_a1b2c3d4e5",
  "filename": "himalayan_scene.tif",
  "metadata": {
    "width": 512,
    "height": 512,
    "format": "TIF",
    "file_size_bytes": 788240,
    "is_georeferenced": true,
    "crs": "EPSG:32643",
    "transform": [10.0, 0.0, 300000.0, 0.0, -10.0, 3400000.0],
    "bounds": [300000.0, 3394880.0, 305120.0, 3400000.0],
    "resolution": [10.0, 10.0],
    "nodata": -9999.0,
    "band_count": 3
  },
  "has_dem": true,
  "has_gcp": true,
  "message": "Georeferenced GeoTIFF identified."
}
```

---

### 3. Reconstruction Execution & Status
- **Endpoint**: `POST /api/process/{job_id}`
- **Description**: Runs the 12-stage elevation reconstruction pipeline.
- **Endpoint**: `GET /api/jobs/{job_id}`
- **Description**: Polls real-time stage progress, percentage (0-100), and stage execution status.

---

### 4. Terrain Analytics & Disaster Features
- **Endpoint**: `POST /api/analysis/profile/{job_id}`
  - **Body**: `{ "x1_pct": 0.1, "y1_pct": 0.2, "x2_pct": 0.9, "y2_pct": 0.8, "samples": 60 }`
  - **Returns**: Continuous elevation transect points, cumulative elevation gains/losses, total distance.
- **Endpoint**: `POST /api/analysis/flood/{job_id}`
  - **Body**: `{ "water_elevation": 3100.0 }`
  - **Returns**: Inundated area percentage, flooded pixel count, transparent PNG mask overlay.

---

### 5. Ground Truth Evaluation
- **Endpoint**: `POST /api/evaluate/{job_id}`
- **Content-Type**: `multipart/form-data`
  - `reference_file`: Reference DEM/DSM GeoTIFF or NPY.
- **Returns**: Quantitative metrics (MAE, RMSE, Pearson $r$, MBE), diverging error map URL, error distribution histogram, scatter plot points.

---

### 6. Demo Datasets
- **Endpoint**: `GET /api/samples`
  - Lists bundled demo packages (Himalayan Valley, Coastal Estuary, Aerial Urban Survey).
- **Endpoint**: `POST /api/samples/{sample_id}/load`
  - Instantly initializes a demo job ready for reconstruction.

---

### 7. Export Package
- **Endpoint**: `GET /api/results/{job_id}/export`
  - Downloads a complete ZIP archive with DSM GeoTIFF, Wavefront OBJ mesh, heightfield JSON, telemetry PNGs, and project report.
