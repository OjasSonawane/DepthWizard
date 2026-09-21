# DepthWizard: Scientific & Technical Methodology

## 1. Remote Sensing & ISRO Disaster Management Context
In emergency remote sensing (post-earthquake assessment, landslide monitoring, glacial lake outburst flood detection), rapid elevation mapping is crucial. Satellite multi-view stereo photogrammetry requires overlapping stereo pairs, which are often unavailable in single-pass acquisitions. DepthWizard addresses this bottleneck by predicting continuous 3D digital surface models from a single monocular optical observation.

## 2. Monocular Depth Estimation & Scale Ambiguity
Monocular vision transformers (e.g., Depth Anything V2) infer relative depth $d(x, y)$ by analyzing perspective cues, atmospheric haze, relative object scale, and structural texture gradients. The output disparity is affine-invariant:
$$d_{\text{rel}}(x, y) \propto \frac{1}{Z(x, y)}$$

## 3. Metric Scale Calibration
To bridge relative depth into metric surface elevation $Z(x, y)$ in meters above mean sea level (AMSL), DepthWizard employs an affine linear transformation:
$$Z(x, y) = a \cdot d_{\text{rel}}(x, y) + b$$

### Scale Parameter Estimation
- **Reference DEM (SRTM/CartoDEM)**: When an external DEM is provided, it is reprojected into the target CRS using bilinear resampling. A robust Huber regressor minimizes outlier sensitivity:
$$\min_{a, b} \sum_{i} \rho\left(Z_{\text{dem}, i} - (a \cdot d_i + b)\right)$$
- **Ground Control Points (GCPs)**: When known ground control points $(x_k, y_k, Z_k)$ are provided, the system samples predicted relative depths at corresponding pixel coordinates and fits ordinary least-squares or Huber regression.
- **Uncalibrated Relative DSM (rDSM)**: For non-georeferenced images or scenes without reference elevation, the output is scaled to relative elevation units $[0, 100]$ and explicitly designated as unitless relative elevation.

## 4. Terrain Surface Derivatives
### Horn Finite-Difference Slope Operator
Surface slope in degrees is computed via Horn's 3x3 kernel:
$$\frac{\partial z}{\partial x} = \frac{(c + 2f + i) - (a + 2d + g)}{8 \Delta x}, \quad \frac{\partial z}{\partial y} = \frac{(g + 2h + i) - (a + 2b + c)}{8 \Delta y}$$
$$\text{Slope} = \arctan\left(\sqrt{\left(\frac{\partial z}{\partial x}\right)^2 + \left(\frac{\partial z}{\partial y}\right)^2}\right) \cdot \frac{180}{\pi}$$

### Analytical Hillshade
Illumination is modeled using standard solar azimuth ($315^\circ$) and solar elevation ($45^\circ$):
$$\text{Hillshade} = 255 \cdot \left(\cos(\zeta)\cos(S) + \sin(\zeta)\sin(S)\cos(\alpha_{\text{sun}} - \alpha_{\text{aspect}})\right)$$

## 5. Evaluation Protocol
Accuracy is verified strictly against co-registered ground truth elevation rasters:
- **Mean Absolute Error (MAE)**: $\frac{1}{N} \sum |Z_{\text{pred}} - Z_{\text{ref}}|$
- **Root Mean Squared Error (RMSE)**: $\sqrt{\frac{1}{N} \sum (Z_{\text{pred}} - Z_{\text{ref}})^2}$
- **Pearson Correlation ($r$)**: $\frac{\text{Cov}(Z_{\text{pred}}, Z_{\text{ref}})}{\sigma_{\text{pred}} \sigma_{\text{ref}}}$
