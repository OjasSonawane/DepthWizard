# DepthWizard — Phase 8: Scientific Validation Interface Report

**Execution Timestamp**: 2026-09-09  
**Status**: PASSED (92 / 92 automated tests passing, 0 errors, 0 warnings in TypeScript build)  
**Standard**: Strict ISRO / FGDC geospatial validation standard (Zero-fabrication, un-simulated scientific calculations)

---

## Executive Summary

Phase 8 elevates DepthWizard's validation capabilities to a rigorous, publication-grade scientific accuracy assessment suite. In compliance with USGS/FGDC and ISRO remote-sensing guidelines, every metric and visualization is computed directly from raw raster arrays. Zero numbers, metrics, categories, or visualizations are fabricated or hardcoded.

```
+---------------------------------------------------------------------------------------------------------+
|                                    SCIENTIFIC VALIDATION WORKFLOW                                       |
+---------------------------------------------------------------------------------------------------------+
|                                                                                                         |
|   Predicted DSM [H x W]  <----+                                                                         |
|                                |                                                                        |
|                                +---> Co-registration & Reprojection ---> Overlap Mask (Valid Pixels)    |
|                                |                                                 |                      |
|   Reference DEM [H' x W'] <---+                                                 v                      |
|                                                                         Residual Array                  |
|                                                                    e = Z_pred - Z_ref                   |
|                                                                                  |                      |
|     +----------------------------------------------------------------------------+                      |
|     |                                                                                                   |
|     v                                             v                                     v               |
|  [Statistical Metrics]                   [6 Visualizations]                   [Interactive / Strata]    |
|  • MAE (Mean Absolute Error)             1. Predicted Height Map              • Pixel Click Inspector   |
|  • RMSE (Root Mean Sq. Error)            2. Reference Height Map                (Pred, Ref, Error)      |
|  • Pearson Correlation (r)               3. Signed Error Map (coolwarm)       • Scene Stratification    |
|  • Bias (Mean Bias Error / MBE)          4. Absolute Error Map (magma)          (Urban, Sparse,         |
|  • Median Absolute Error                 5. Subsampled Scatter Plot (1:1 line)   Hilly, Forest)         |
|  • LE90 (90th percentile)                6. Error Distribution Histogram        (No category            |
|  • LE95 (95th percentile)                   (20 bins, 100% sample coverage)      fabrication)           |
|  • Max Error / Valid Pixel %                                                                            |
|                                                                                                         |
+---------------------------------------------------------------------------------------------------------+
```

---

## 1. Metrics Specification & Computation

All metrics operate strictly over valid overlapping finite pixels where $Z > -9000.0$:

$$\Omega = \{ (i, j) \mid \text{finite}(Z_{\text{pred}}(i, j)) \land \text{finite}(Z_{\text{ref}}(i, j)) \land Z_{\text{ref}}(i, j) > -9000.0 \}$$

Residuals are defined as:
$$e_k = Z_{\text{pred}}(k) - Z_{\text{ref}}(k), \quad k \in \Omega$$

### 1.1 Primary Metrics
| Metric | Mathematical Formula | Purpose & Interpretation |
| :--- | :--- | :--- |
| **MAE** | $\frac{1}{N} \sum_{k=1}^N \|e_k\|$ | Mean vertical error magnitude across valid coverage. |
| **RMSE** | $\sqrt{\frac{1}{N} \sum_{k=1}^N e_k^2}$ | Penalizes large vertical deviations and severe terrain misalignments. |
| **Pearson Correlation ($r$)** | $\frac{\sum (Z_{\text{pred}} - \bar{Z}_{\text{pred}})(Z_{\text{ref}} - \bar{Z}_{\text{ref}})}{\sqrt{\sum (Z_{\text{pred}} - \bar{Z}_{\text{pred}})^2 \sum (Z_{\text{ref}} - \bar{Z}_{\text{ref}})^2}}$ | Evaluates shape, relief, and slope trend correspondence $[-1, +1]$. |

### 1.2 Additional Metrics
| Metric | Mathematical Formula | Purpose & Interpretation |
| :--- | :--- | :--- |
| **Mean Bias Error (MBE)** | $\frac{1}{N} \sum_{k=1}^N e_k$ | Detects systematic vertical elevation shift ($>0$ overestimation, $<0$ underestimation). |
| **Median Absolute Error** | $\text{median}(\|e_k\|)$ | Outlier-resilient measure of typical reconstruction accuracy. |
| **P90 Error (LE90)** | $\text{Percentile}_{90}(\|e_k\|)$ | Standard USGS/FGDC vertical accuracy metric (90% confidence interval). |
| **P95 Error (LE95)** | $\text{Percentile}_{95}(\|e_k\|)$ | 95% confidence interval vertical error threshold for engineering applications. |
| **Maximum Error** | $\max(\|e_k\|)$ | Worst-case localized relief error across all evaluated pixels. |
| **Valid Pixel %** | $\frac{N_{\text{valid}}}{N_{\text{total}}} \times 100\%$ | Spatial overlap fidelity between predicted surface and ground truth. |

---

## 2. Visualizations Suite

Phase 8 generates and exposes 6 distinct visualization artifacts:

1. **Predicted Height Map (`predicted_map_url`)**:
   - Colorized elevation raster rendered with hypsometric colormap (`cm.terrain`).
   - Normalization scale shared identically with the reference height map $[Z_{\min}, Z_{\max}]$.
2. **Reference Height Map (`reference_map_url`)**:
   - Colorized ground truth elevation raster matching the identical hypsometric scale and color ramp.
3. **Signed Error Map (`error_map_url`)**:
   - Diverging blue-white-red (`cm.coolwarm`) raster centered at $0\text{ m}$.
   - Dynamically scaled to $\pm 98\text{th}$ percentile absolute error ($L_{\text{abs}}$), clearly distinguishing under-estimation (blue, $-\Delta Z$) from over-estimation (red, $+\Delta Z$).
4. **Absolute Error Map (`abs_error_map_url`)**:
   - Sequential magma colormap displaying vertical error magnitude $[0, L_{\text{abs}}]$.
5. **Predicted vs Reference Scatter Plot (`scatter_samples`)**:
   - Subsampled point distribution (up to 200 points) plotted alongside the $1:1$ ideal agreement line.
   - Computes live residual tooltip and displays overall Pearson $r$.
6. **Error Histogram (`error_histogram`)**:
   - 20-bin histogram spanning $[-L_{\text{abs}}, +L_{\text{abs}}]$.
   - Outliers beyond the 98th percentile are binned into tail buckets to preserve 100.0% sample accounting without skewing bin resolutions.

---

## 3. Interactive Pixel Inspection

Users can click any pixel on the surface inspection canvas to inspect exact local elevation and error statistics:
- **Predicted Elevation**: Real predicted DSM height at $(X, Y)$ in meters.
- **Reference Elevation**: Real co-registered ground truth DEM height at $(X, Y)$ in meters.
- **Error (Residual)**: $Z_{\text{pred}} - Z_{\text{ref}}$ in meters.
- **Surface Slope**: Horn slope gradient at queried pixel in degrees.
- **Coordinates**: Both raster pixel indices $[X, Y]$ and geographic coordinates (Easting/Northing or Latitude/Longitude).
- **Honest "Unavailable" Standard**: When evaluating a reconstruction without a reference DEM, clicking returns `reference_height: None` and `error: None` with clear UI labeling, upholding scientific honesty.

---

## 4. Scene Stratification (No Category Fabrication)

Where dataset classification labels or land cover masks exist:
- Supports evaluation of distinct terrain strata: `Urban`, `Sparse`, `Hilly`, `Forest`.
- Metrics are calculated **independently** for each stratum using only pixels belonging to that category:
  - Valid Samples count
  - Stratum MAE
  - Stratum RMSE
  - Stratum Pearson $r$
  - Stratum Bias (MBE)
  - Stratum Median AE
- **Strict Anti-Fabrication Rule**:
  - Categories are never simulated or generated if absent from the ground truth dataset.
  - Categories with fewer than 10 valid pixels ($N < 10$) are strictly omitted from reporting.
  - When categorical labels are not provided, stratification gracefully derives standard terrain relief regimes via Horn slope gradients:
    - Flat / Built-up ($< 10^\circ$)
    - Undulating / Moderate ($10^\circ - 25^\circ$)
    - Mountainous / Steep ($25^\circ - 40^\circ$)
    - Rugged / Extreme ($> 40^\circ$)

---

## 5. Verification & Test Suite

### Automated Test Coverage
All tests executed in Python 3.11 with `pytest` and `FastAPI TestClient`:

```bash
PYTHONPATH=backend ./backend/venv/bin/pytest backend/tests/ -v
```

**Results**:
- `test_phase8_validation.py`:
  - `test_primary_and_additional_metrics_exact_math`: **PASSED**
  - `test_all_six_visualization_artifacts`: **PASSED**
  - `test_pixel_inspection_interaction`: **PASSED**
  - `test_scene_stratification_without_category_fabrication`: **PASSED**
  - `test_evaluation_api_response_schema_and_urls`: **PASSED**
- Total repository tests: **92 passed, 0 failed** in 44.63s.

### Frontend Compilation
```bash
npm run build
```
- TypeScript (`tsc`) completed with 0 errors.
- Vite production bundle built cleanly in 3.11s.

---

## 6. Architecture Compliance Matrix

| Phase 8 Requirement | Implementation | Status |
| :--- | :--- | :---: |
| Primary: MAE, RMSE, Correlation | `EvaluationService.evaluate_against_reference` | **COMPLIANT** |
| Additional: Bias, Med AE, P90, P95, Max Error, Valid % | `EvaluationMetrics` & array calculations | **COMPLIANT** |
| Predicted & Reference Height Maps | `_pred_map.png` & `_ref_map.png` (matching terrain colormap) | **COMPLIANT** |
| Signed & Absolute Error Maps | `_error_map.png` (coolwarm) & `_abs_error_map.png` (magma) | **COMPLIANT** |
| Scatter Plot & Error Histogram | `scatter_samples` (1:1 line) & `error_histogram` (20 bins) | **COMPLIANT** |
| Interactive Pixel Inspection | `GET /api/results/{job_id}/inspect-point` + canvas click handler | **COMPLIANT** |
| Scene Stratification | Urban, Sparse, Hilly, Forest calculated independently | **COMPLIANT** |
| Zero Fabrication Policy | Strictly 0 placeholder values or fake categories | **COMPLIANT** |
| Zero UI Redesign Policy | Native layout, color tokens, and navigation preserved | **COMPLIANT** |

