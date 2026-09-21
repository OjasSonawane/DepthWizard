# DEPTHWIZARD — PHASE 6 INTEGRATION REPORT
## Backend → Existing UI Integration & Single Job Workflow

**Date**: 2026-09-09  
**Status**: Completed & Fully Verified  
**Test Suite**: 80 / 80 Passing Tests  
**Frontend Build**: Vite + TypeScript 0 Errors  

---

### Executive Summary

In Phase 6, DepthWizard’s frontend was transformed into a strict **visualization client** for the real backend scientific pipeline. All mock and hardcoded scientific values, fallback latencies, and synthetic terrain metrics have been removed. When scientific values are uncomputed or not applicable (e.g. non-georeferenced imagery without a reference DEM), the UI displays strictly `"Unavailable"` in accordance with scientific integrity standards.

The entire workflow operates on a **single central `job_id`** from ingestion through neural depth inference, calibration, DSM generation, geostatistical validation, and artifact export.

---

### 1. Central Processing Job Model

The centralized job model is implemented in [`backend/app/schemas/schemas.py`](file:///Users/ojas/Desktop/SIH-2026/DepthWizard-new/backend/app/schemas/schemas.py) and tracked by [`PipelineManager`](file:///Users/ojas/Desktop/SIH-2026/DepthWizard-new/backend/app/services/depth_service.py).

#### Core Fields
| Field | Type | Description |
| :--- | :--- | :--- |
| `job_id` | `str` | Unique job identifier (e.g., `dw_job_a1b2c3d4`) |
| `status` | `JobState` | Lifecycle state in standard 8-state machine |
| `input` | `Dict[str, Any]` | Uploaded raster metadata: path, filename, width, height, format, CRS, bounds, resolution, nodata, band count, hash |
| `validation` | `Dict[str, Any]` | Optical and geospatial validity: resolution check, blur/entropy check, projection verification |
| `depth` | `Dict[str, Any]` | Model name, device (CPU/MPS/CUDA), min/max raw/normalized depth values, inference execution time |
| `calibration` | `Dict[str, Any]` | Method (`relative`, `huber_dem`, `gcp_ransac`), scale, shift, confidence, metric flag, target CRS |
| `dsm` | `Dict[str, Any]` | Generated DSM dimensions, min/max/mean elevation, unit (`meters` or `relative_units`), status (`metric_dsm` or `relative_rdsm`) |
| `validation_result` | `Dict[str, Any]` | Real scientific metrics: MAE, RMSE, Pearson r, R², valid pixel percentage, error maps |
| `artifacts` | `Dict[str, str]` | Download and visualization asset URLs: GeoTIFF DSM, colorized preview, error maps, 3D mesh heightfield |
| `errors` | `List[str]` | Execution warnings or failure tracebacks |

#### Standard 8-State Machine
```
[QUEUED] ──> [VALIDATING] ──> [INFERENCE] ──> [CALIBRATING] 
                                                    │
[COMPLETED] <── [VALIDATING_RESULT] <── [GENERATING_DSM]
     │
     └──> [FAILED] (any stage error transition)
```

1. **`QUEUED`**: Job registered, assets staged, waiting for worker.
2. **`VALIDATING`**: Image integrity and optical quality verified, raster geospatial tags inspected.
3. **`INFERENCE`**: Depth Anything V2 monocular depth estimation executed on hardware device.
4. **`CALIBRATING`**: Calibration abstraction computes scale/shift via relative, Huber DEM, or RANSAC GCP.
5. **`GENERATING_DSM`**: Metric DSM or relative rDSM raster constructed, reprojection and NoData applied.
6. **`VALIDATING_RESULT`**: Statistical error evaluation against reference DEM / benchmark Ground Truth.
7. **`COMPLETED`**: All artifacts generated, GeoTIFF written, ready for visualization & export.
8. **`FAILED`**: Explicit error capture with full diagnostic message stored in `job.errors`.

---

### 2. Stable Central API Surface

DepthWizard exposes clean, RESTful endpoints that provide a single source of truth for both the frontend UI and automated clients:

| API Function | HTTP Method & Route | Description |
| :--- | :--- | :--- |
| **Upload** | `POST /api/upload`<br>`POST /api/datasets/upload` | Uploads imagery, extracts initial metadata, registers job. |
| **Create Job** | `POST /api/jobs/create`<br>`POST /api/datasets/{id}/prepare-job` | Explicitly creates/configures a central job for processing. |
| **Job Status** | `GET /api/jobs/{job_id}`<br>`GET /api/reconstruction/status/{job_id}` | Polled by UI; returns stage progress and enriched state. |
| **Start Job** | `POST /api/jobs/{job_id}/start`<br>`POST /api/process/{job_id}` | Triggers pipeline processing for the registered job. |
| **Depth Result** | `GET /api/results/{job_id}/depth` | Returns model details, device, relative depth range, latency, and visualizer URL. |
| **DSM Result** | `GET /api/results/{job_id}/dsm` | Returns DSM elevation statistics, CRS, resolution, status, and 3D heightfield URL. |
| **Validation Result**| `GET /api/results/{job_id}/validation`<br>`POST /api/evaluate/{job_id}` | Returns computed MAE, RMSE, Pearson r, error maps, and scatter plot. |
| **Artifact Retrieval**| `GET /api/results/{job_id}/artifacts`<br>`GET /api/export/{job_id}` | Package retrieval containing GeoTIFF, OBJ mesh, and report metadata. |

---

### 3. Frontend Visualization Client & The "Unavailable" Standard

In adherence to the **Zero UI Redesign Policy**, all layouts, navigation tabs, color palette (slate/cyan/emerald), and component hierarchies were preserved. The frontend was transformed from calculating/mocking values into a pure presentation layer.

#### Strict "Unavailable" Display Standard
Previous versions displayed placeholder values (e.g. `0`, `0.25s`, simulated latencies, or fake terrain bounds). All such fallbacks have been replaced:
- **CRS**: When non-georeferenced, displays `"Unavailable"` (or `"Relative (No CRS)"` where appropriate).
- **Pixel Resolution**: If imagery lacks spatial georeferencing, displays `"Unavailable"`.
- **Validation Metrics (MAE, RMSE, Correlation/R²)**: If no reference DEM was uploaded or evaluated, the DSM viewer and validation panels display strictly `"Unavailable"`.
- **Latency & Timings**: Pipeline stage durations reflect actual measured wall-clock execution times, never hardcoded dummy seconds.

#### Updated Frontend Modules
- [`frontend/src/types/index.ts`](file:///Users/ojas/Desktop/SIH-2026/DepthWizard-new/frontend/src/types/index.ts): Synchronized with backend `CentralJobModel` and `JobState`.
- [`frontend/src/services/api.ts`](file:///Users/ojas/Desktop/SIH-2026/DepthWizard-new/frontend/src/services/api.ts): Added endpoints for job creation, execution, depth asset query, and artifact downloads.
- [`frontend/src/pages/DSMViewerPage.tsx`](file:///Users/ojas/Desktop/SIH-2026/DepthWizard-new/frontend/src/pages/DSMViewerPage.tsx): Displays real backend DSM stats (min/max elevation, resolution, CRS, calibration method, MAE/RMSE/R² or `"Unavailable"`).
- [`frontend/src/pages/DepthViewerPage.tsx`](file:///Users/ojas/Desktop/SIH-2026/DepthWizard-new/frontend/src/pages/DepthViewerPage.tsx): Displays real model metadata (`Depth Anything V2`), inference device (`mps`/`cpu`/`cuda`), and measured latency.
- [`frontend/src/pages/AnalysisPage.tsx`](file:///Users/ojas/Desktop/SIH-2026/DepthWizard-new/frontend/src/pages/AnalysisPage.tsx): Displays real step latencies (`preprocessing`, `depth_estimation`, `scale_calibration`, `dsm_generation`, `export`).
- [`frontend/src/layouts/AppLayout.tsx`](file:///Users/ojas/Desktop/SIH-2026/DepthWizard-new/frontend/src/layouts/AppLayout.tsx): Header status pills support all 8 states (`QUEUED` to `COMPLETED`/`FAILED`).
- [`frontend/src/components/HUD.tsx`](file:///Users/ojas/Desktop/SIH-2026/DepthWizard-new/frontend/src/components/HUD.tsx): Top-right overlay displays real geodetic bounds and CRS or `"Unavailable"`.

---

### 4. Verification & Automated Test Coverage

The integration was validated through comprehensive unit, functional, and end-to-end integration tests:

1. **End-to-End Single `job_id` Flow** ([`backend/tests/test_phase6_integration.py`](file:///Users/ojas/Desktop/SIH-2026/DepthWizard-new/backend/tests/test_phase6_integration.py)):
   - Verifies `POST /api/upload` -> `POST /api/jobs/{job_id}/start` -> `GET /api/jobs/{job_id}` -> `GET /api/results/{job_id}/depth` -> `GET /api/results/{job_id}/dsm` -> `GET /api/results/{job_id}/validation` -> `GET /api/results/{job_id}/artifacts`.
   - Confirms state machine advances through all stages without desynchronization.
2. **Honest "Unavailable" Standard Verification**:
   - Asserts that uncalibrated relative imagery produces `null` MAE/RMSE and `is_georeferenced: false`, allowing UI to show `"Unavailable"`.
3. **Full Suite Regression Testing**:
   - **80 / 80 tests passed** in 29.57 seconds across all test modules:
     - `test_phase6_integration.py` (3/3 passed)
     - `test_phase5_geotiff.py` (10/10 passed)
     - `test_scientific_pipeline.py` (19/19 passed)
     - `test_dataset_workflow.py` (8/8 passed)
     - `test_comprehensive_pipeline.py` (6/6 passed)
     - `test_configurable_metrics.py` (3/3 passed)
     - `test_depth_anything.py` (14/14 passed)
     - `test_image_validation.py` (4/4 passed)
     - `test_gamus_benchmark.py` (13/13 passed)
4. **Frontend Production Build**:
   - `tsc && vite build` completed in 3.33s with 0 errors.

