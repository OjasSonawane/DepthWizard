import React from 'react';
import { useProject } from '../context/ProjectContext';
import {
  FileText,
  Layers,
  Globe,
  Box,
  ShieldCheck,
  CheckCircle2,
  Cpu,
  Compass,
  ArrowRight,
  ShieldAlert,
  BarChart3,
  SlidersHorizontal
} from 'lucide-react';

export const MethodologyPage: React.FC = () => {
  const { setActiveTab } = useProject();

  return (
    <div className="max-w-4xl mx-auto px-6 py-10 space-y-12 text-slate-300 font-sans leading-relaxed">
      {/* Title */}
      <div className="border-b border-slate-800 pb-6 space-y-3">
        <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/25 text-cyan-300 text-xs font-mono">
          <span>ISRO SOFTWARE PROBLEM STATEMENT • METHODOLOGICAL BRIEF</span>
        </div>
        <h1 className="text-3xl font-extrabold text-white tracking-tight">
          Single-View AI Remote-Sensing 3D Reconstruction Methodology
        </h1>
        <p className="text-sm text-slate-400">
          Domain-specific input quality control, neural depth inference, affine scale calibration, and configurable scientific model validation.
        </p>
      </div>

      {/* Section 1: Problem Statement & Scale Ambiguity */}
      <section className="space-y-4">
        <h2 className="text-xl font-bold text-white flex items-center space-x-2">
          <span className="text-cyan-400 font-mono">01.</span>
          <span>Problem Formulation & Scale Ambiguity</span>
        </h2>
        <p className="text-sm">
          Traditional satellite photogrammetry requires multi-view stereo (along-track or across-track stereo pairs)
          to triangulate 3D point coordinates. However, during rapid-onset disasters (such as flash floods, earthquakes, or landslides),
          only a single nadir or off-nadir optical pass is frequently available from satellites like Cartosat, Sentinel-2, or optical aerial platforms.
        </p>
        <p className="text-sm">
          In single-view monocular computer vision, depth estimation is inherently scale-ambiguous: infinitely many 3D scenes
          can produce the identical 2D projection. Monocular vision transformers (e.g., Depth Anything V2) predict an affine-invariant
          disparity field $d \in [0, 1]$ where local gradients encode relative topographic relief, but the absolute metric scale $s$
          and vertical datum offset $t$ are unknown.
        </p>
      </section>

      {/* Section 2: Input Quality Control & Content Validation Pipeline */}
      <section className="space-y-4">
        <h2 className="text-xl font-bold text-white flex items-center space-x-2">
          <span className="text-cyan-400 font-mono">02.</span>
          <span>Input Quality Control & Remote-Sensing Validation Pipeline</span>
        </h2>
        <p className="text-sm">
          DepthWizard is a specialized optical remote-sensing application. To prevent non-sensical depth outputs and save compute resources,
          all uploaded rasters undergo an automated 6-stage content and suitability inspection before inference begins:
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1 font-mono text-xs">
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1.5">
            <div className="flex items-center space-x-2 text-cyan-400 font-bold">
              <ShieldCheck className="w-4 h-4" />
              <span>Stage 1 & 2: Magic Bytes & Radiometric Variance</span>
            </div>
            <p className="text-slate-400 font-sans text-xs">
              Verifies binary magic byte headers for TIFF, PNG, and JPEG. Inspects pixel variance across all channels; uniform/blank single-color frames ($\sigma^2 &lt; 1.0$) are rejected.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1.5">
            <div className="flex items-center space-x-2 text-amber-400 font-bold">
              <ShieldAlert className="w-4 h-4" />
              <span>Stage 3: Resolution Guardrails</span>
            </div>
            <p className="text-slate-400 font-sans text-xs">
              Hard rejection for rasters &lt;32×32 px. Low-resolution advisory (&lt;128×128 px) applies bicubic interpolation and warns the user. Extreme aspect ratios (&gt;8:1) trigger spatial distortion alerts.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1.5">
            <div className="flex items-center space-x-2 text-indigo-400 font-bold">
              <Globe className="w-4 h-4" />
              <span>Stage 4: Geospatial Tag Priority</span>
            </div>
            <p className="text-slate-400 font-sans text-xs">
              GeoTIFFs with valid Coordinate Reference Systems (EPSG / UTM) and affine geotransforms receive spatial verification and are prioritized for metric Digital Surface Model (DSM) generation.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1.5">
            <div className="flex items-center space-x-2 text-rose-400 font-bold">
              <ShieldCheck className="w-4 h-4" />
              <span>Stage 5 & 6: Non-Terrain & Portrait Exclusion</span>
            </div>
            <p className="text-slate-400 font-sans text-xs">
              Haar cascades and HOG detectors flag dominant human portraits (face area &gt;3.0% of frame), while allowing tiny pedestrians in satellite scenes (&lt;0.3%). Horizontal line density detects documents and code screenshots.
            </p>
          </div>
        </div>
      </section>

      {/* Section 3: Mathematical Calibration Model */}
      <section className="space-y-4">
        <h2 className="text-xl font-bold text-white flex items-center space-x-2">
          <span className="text-cyan-400 font-mono">03.</span>
          <span>Scale & Offset Calibration Model</span>
        </h2>
        <p className="text-sm">
          To convert the relative depth map $d(x, y)$ into a metric Digital Surface Model $Z(x, y)$ in meters above mean sea level (AMSL),
          DepthWizard applies an affine linear mapping calibrated against reference elevations:
        </p>

        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 font-mono text-center text-cyan-300 text-sm">
          Z(x, y) = a · d(x, y) + b
        </div>

        <p className="text-sm">
          Where:
        </p>
        <ul className="list-disc list-inside text-xs space-y-1.5 pl-2 text-slate-300 font-mono">
          <li><strong>Z(x, y)</strong>: Calibrated elevation in meters at pixel (x, y).</li>
          <li><strong>d(x, y)</strong>: Normalized relative depth surface from the neural model.</li>
          <li><strong>a (Scale factor)</strong>: Represents the vertical terrain relief dynamic range.</li>
          <li><strong>b (Datum offset)</strong>: Represents the base elevation datum (meters AMSL).</li>
        </ul>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2">
            <h4 className="text-xs font-bold text-white uppercase font-mono">Mode A: Reference DEM Calibration</h4>
            <p className="text-xs text-slate-400">
              When a low-resolution DEM (such as SRTM 30m or CartoDEM) is available, DepthWizard reprojects and resamples the DEM
              onto the target raster grid. A robust <strong>Huber Regressor</strong> is fitted on all overlapping valid non-nodata pixels,
              mitigating structural outliers caused by cloud shadows or sensor noise.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2">
            <h4 className="text-xs font-bold text-white uppercase font-mono">Mode B: Ground Control Points (GCPs)</h4>
            <p className="text-xs text-slate-400">
              When survey GCPs $(x_i, y_i, Z_i)$ are uploaded via CSV, the system projects their spatial coordinates into pixel space,
              samples the predicted relative depth $d_i$, and minimizes the squared residual sum $\sum (Z_i - (a \cdot d_i + b))^2$.
            </p>
          </div>
        </div>
      </section>

      {/* Section 4: Geospatial Preservation & Horn Slope */}
      <section className="space-y-4">
        <h2 className="text-xl font-bold text-white flex items-center space-x-2">
          <span className="text-cyan-400 font-mono">04.</span>
          <span>Geospatial Metadata & Horn Slope Derivative</span>
        </h2>
        <p className="text-sm">
          Unlike standard 3D web demos that discard GIS tags, DepthWizard leverages <strong>Rasterio</strong> to preserve full GeoTIFF tags:
          Coordinate Reference Systems (e.g. UTM projections, EPSG codes), affine geotransform matrices, bounding envelopes, and ground sample distance (GSD).
        </p>
        <p className="text-sm">
          To support landslide hazard zoning and geomorphic analysis, surface slope $\theta$ is derived using <strong>Horn's 3×3 finite-difference operator</strong> (standard in GDAL/ArcGIS):
        </p>

        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 font-mono text-center text-xs text-slate-200">
          dz/dx = ((c + 2f + i) - (a + 2d + g)) / (8 · Δx) <br />
          dz/dy = ((g + 2h + i) - (a + 2b + c)) / (8 · Δy) <br />
          <span className="text-cyan-400 font-bold">Slope (deg) = arctan(√( (dz/dx)² + (dz/dy)² )) · (180 / π)</span>
        </div>
      </section>

      {/* Section 5: Configurable Scientific Validation & Geospatial Standards */}
      <section className="space-y-4">
        <h2 className="text-xl font-bold text-white flex items-center space-x-2">
          <span className="text-cyan-400 font-mono">05.</span>
          <span>Configurable Scientific Accuracy Standards</span>
        </h2>
        <p className="text-sm">
          DepthWizard features a comprehensive, configurable model validation subsystem supporting multiple evaluation profiles
          (<strong>Terrain Standard</strong>, <strong>Basic Terrain</strong>, <strong>Terrain Comprehensive</strong>, <strong>Depth Benchmark</strong>, and <strong>Custom</strong>):
        </p>

        <div className="space-y-3 pt-1 text-xs">
          <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
            <div className="font-mono font-bold text-white">USGS / FGDC Linear Error Standards (LE90 & LE95)</div>
            <p className="text-slate-400 leading-relaxed font-sans">
              LE90 = 90th percentile of |&Delta;Z| defines the vertical error threshold below which 90% of all evaluated points fall.
              LE95 = 95th percentile of |&Delta;Z| enforces 95% confidence bounds, standard in airborne LiDAR and photogrammetric elevation accuracy reporting.
            </p>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
            <div className="font-mono font-bold text-white">Monocular Depth Benchmark Metrics (AbsRel, SqRel, delta thresholds)</div>
            <p className="text-slate-400 leading-relaxed font-sans">
              Measures mean absolute relative error (AbsRel), squared relative error (SqRel), and accuracy thresholds (&delta; &lt; 1.25, &delta; &lt; 1.25², and &delta; &lt; 1.25³)
              across evaluated ground truth pixels, aligning single-view remote sensing directly with computer-vision benchmark literature.
            </p>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
            <div className="font-mono font-bold text-white">Slope Gradient Error (Slope MAE & Slope RMSE)</div>
            <p className="text-slate-400 leading-relaxed font-sans">
              Evaluates surface slope fidelity across interior pixels, ensuring that derived slope angles for landslide and flood runoff modeling accurately match ground truth topography.
            </p>
          </div>
        </div>

        <div className="p-3 rounded-xl bg-emerald-950/30 border border-emerald-500/30 text-emerald-300 text-xs font-mono flex items-center space-x-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>Zero Fabricated Metrics: Validation metrics and error maps are computed strictly against user-supplied reference elevation rasters.</span>
        </div>
      </section>

      {/* Section 6: 3D Mesh Generation & WebGL Performance */}
      <section className="space-y-4">
        <h2 className="text-xl font-bold text-white flex items-center space-x-2">
          <span className="text-cyan-400 font-mono">06.</span>
          <span>3D Mesh Construction & Texture Projection</span>
        </h2>
        <p className="text-sm">
          To maintain smooth 60 FPS flythrough on normal laptops without overwhelming WebGL memory, DepthWizard generates an optimized
          regular heightfield grid (192×192 vertices, 73,728 triangulated faces). The original high-resolution optical image is mapped
          as an anisotropic RGB texture over the displaced vertices, creating photorealistic terrain relief.
        </p>
      </section>

      {/* Launch CTA */}
      <div className="pt-6 border-t border-slate-800 flex items-center justify-between">
        <button
          onClick={() => setActiveTab('upload')}
          className="flex items-center space-x-2 px-6 py-3 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-semibold text-xs font-mono transition-colors shadow-lg shadow-cyan-500/20"
        >
          <span>Launch Ingestion Workspace</span>
          <ArrowRight className="w-4 h-4" />
        </button>

        <span className="text-xs text-slate-500 font-mono">DepthWizard v1.0 • ISRO Theme</span>
      </div>
    </div>
  );
};
