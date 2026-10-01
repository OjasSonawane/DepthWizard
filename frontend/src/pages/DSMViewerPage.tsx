import React, { useState, useEffect } from 'react';
import { useProject } from '../context/ProjectContext';
import { api } from '../services/api';
import {
  Globe2,
  Sliders,
  Layers,
  Download,
  Info,
  ArrowRight,
  Sun,
  Mountain,
  AlertTriangle,
  BarChart3,
  Maximize2
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell
} from 'recharts';

export const DSMViewerPage: React.FC = () => {
  const { results, setActiveTab } = useProject();
  const [activeLayer, setActiveLayer] = useState<'dsm_color' | 'hillshade' | 'slope' | 'contour'>('dsm_color');
  const [opacity, setOpacity] = useState<number>(100);
  const [showContours, setShowContours] = useState<boolean>(false);
  const [histogramData, setHistogramData] = useState<Array<{
    bin_start: number;
    bin_end: number;
    bin_label: string;
    count: number;
    percentage: number;
  }>>([]);

  useEffect(() => {
    if (!results) return;
    if (results.elevation_histogram && results.elevation_histogram.length > 0) {
      setHistogramData(results.elevation_histogram);
    } else {
      api.getDSMAssets(results.job_id)
        .then((data) => {
          if (data.elevation_histogram) {
            setHistogramData(data.elevation_histogram);
          }
        })
        .catch(console.error);
    }
  }, [results]);

  if (!results) {
    return (
      <div className="flex flex-col items-center justify-center h-[70vh] text-center space-y-4">
        <Globe2 className="w-12 h-12 text-slate-600" />
        <h3 className="text-lg font-bold text-white">No Digital Surface Model</h3>
        <p className="text-xs text-slate-400 max-w-sm">
          Execute a reconstruction to view calibrated surface elevation rasters.
        </p>
        <button
          onClick={() => setActiveTab('upload')}
          className="px-4 py-2 rounded-lg bg-cyan-500 text-black font-semibold text-xs font-mono"
        >
          Start Reconstruction
        </button>
      </div>
    );
  }

  const { dsm_stats, image_metadata, calibration } = results;
  const unit = dsm_stats.is_metric ? 'm' : 'rel';

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center space-x-3">
            <h2 className="text-xl font-bold text-white">
              {results.is_georeferenced ? 'Digital Surface Model (DSM)' : 'Relative Surface Model (rDSM)'}
            </h2>
            <span
              className={`px-2.5 py-0.5 rounded text-[10px] font-mono ${
                dsm_stats.is_metric
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                  : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
              }`}
            >
              {dsm_stats.is_metric ? 'METRIC ELEVATION (m)' : 'RELATIVE SCALE [0–100]'}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Raster surface elevation model with 3x3 finite-difference slope and analytical hillshade illumination.
          </p>
        </div>

        {/* Action button */}
        <div className="flex items-center space-x-2">
          <a
            href={results.assets.dsm_geotiff}
            download
            className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-mono transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download GeoTIFF</span>
          </a>
          <button
            onClick={() => setActiveTab('explorer')}
            className="flex items-center space-x-2 px-3.5 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black font-semibold text-xs font-mono transition-colors shadow-sm shadow-cyan-500/20"
          >
            <span>Explore 3D →</span>
          </button>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Interactive 2D Raster Viewer */}
        <div className="lg:col-span-8 space-y-4">
          <div className="relative rounded-2xl bg-slate-950 border border-slate-800 overflow-hidden aspect-square max-h-[580px] flex items-center justify-center shadow-2xl">
            {/* Primary Base Raster */}
            <img
              src={results.assets[activeLayer]}
              alt="DSM Layer"
              className="w-full h-full object-contain"
              style={{ opacity: opacity / 100 }}
            />

            {/* Topographic Contour Overlay */}
            {showContours && activeLayer !== 'contour' && (
              <img
                src={results.assets.contour}
                alt="Contour Overlay"
                className="absolute inset-0 w-full h-full object-contain pointer-events-none"
              />
            )}

            {/* Bottom-left telemetry badge */}
            <div className="absolute bottom-3 left-3 px-3 py-1.5 rounded-lg bg-black/70 backdrop-blur-md border border-slate-800 text-[11px] font-mono text-slate-300 flex items-center space-x-3">
              <div>
                MIN: <span className="text-white font-bold">{dsm_stats.min_elevation} {unit}</span>
              </div>
              <span className="text-slate-600">|</span>
              <div>
                MAX: <span className="text-cyan-400 font-bold">{dsm_stats.max_elevation} {unit}</span>
              </div>
              <span className="text-slate-600">|</span>
              <div>
                RELIEF: <span className="text-emerald-400 font-bold">{dsm_stats.relief} {unit}</span>
              </div>
            </div>
          </div>

          {/* Controls Bar */}
          <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 flex flex-wrap items-center justify-between gap-4 text-xs font-mono">
            {/* Layer tabs */}
            <div className="flex items-center space-x-1.5 bg-slate-950/60 p-1 rounded-lg border border-slate-800">
              <button
                onClick={() => setActiveLayer('dsm_color')}
                className={`px-3 py-1 rounded transition-all ${
                  activeLayer === 'dsm_color' ? 'bg-cyan-500 text-black font-bold' : 'text-slate-400 hover:text-white'
                }`}
              >
                Terrain Relief
              </button>
              <button
                onClick={() => setActiveLayer('hillshade')}
                className={`px-3 py-1 rounded transition-all ${
                  activeLayer === 'hillshade' ? 'bg-cyan-500 text-black font-bold' : 'text-slate-400 hover:text-white'
                }`}
              >
                Hillshade (315°)
              </button>
              <button
                onClick={() => setActiveLayer('slope')}
                className={`px-3 py-1 rounded transition-all ${
                  activeLayer === 'slope' ? 'bg-cyan-500 text-black font-bold' : 'text-slate-400 hover:text-white'
                }`}
              >
                Slope Map
              </button>
              <button
                onClick={() => setActiveLayer('contour')}
                className={`px-3 py-1 rounded transition-all ${
                  activeLayer === 'contour' ? 'bg-cyan-500 text-black font-bold' : 'text-slate-400 hover:text-white'
                }`}
              >
                Contours Only
              </button>
            </div>

            {/* Toggles & Sliders */}
            <div className="flex items-center space-x-4">
              <label className="flex items-center space-x-2 text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showContours}
                  onChange={(e) => setShowContours(e.target.checked)}
                  className="rounded border-slate-700 text-cyan-500 focus:ring-0"
                />
                <span>Overlay Contours</span>
              </label>

              <div className="flex items-center space-x-2">
                <span className="text-slate-400">Opacity</span>
                <input
                  type="range"
                  min="20"
                  max="100"
                  value={opacity}
                  onChange={(e) => setOpacity(Number(e.target.value))}
                  className="w-20 accent-cyan-400"
                />
                <span className="text-cyan-300 w-8">{opacity}%</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Technical Statistics & Spatial Metadata */}
        <div className="lg:col-span-4 space-y-4 font-mono text-xs">
          {/* Elevation Statistics Card */}
          <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4 shadow-lg">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <span className="text-cyan-400 font-bold uppercase">Elevation Distribution</span>
              <span className="text-[10px] text-slate-400">{dsm_stats.is_metric ? 'Meters (AMSL)' : 'Arbitrary Scale'}</span>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <div className="text-[10px] text-slate-400">MIN ELEVATION</div>
                <div className="text-base font-bold text-white mt-0.5">{dsm_stats.min_elevation} {unit}</div>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <div className="text-[10px] text-slate-400">MAX ELEVATION</div>
                <div className="text-base font-bold text-cyan-400 mt-0.5">{dsm_stats.max_elevation} {unit}</div>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <div className="text-[10px] text-slate-400">MEAN ELEVATION</div>
                <div className="text-base font-bold text-slate-200 mt-0.5">{dsm_stats.mean_elevation} {unit}</div>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <div className="text-[10px] text-slate-400">TOTAL RELIEF</div>
                <div className="text-base font-bold text-emerald-400 mt-0.5">{dsm_stats.relief} {unit}</div>
              </div>
            </div>

            <div className="pt-2 border-t border-slate-800/80 space-y-2 text-slate-300">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Standard Deviation:</span>
                <span className="text-white font-bold">{dsm_stats.std_elevation} {unit}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Average Slope:</span>
                <span className="text-white font-bold">{dsm_stats.average_slope_deg}°</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Steep Slope (&gt;30°):</span>
                <span className="text-amber-400 font-bold">{dsm_stats.steep_area_pct}% of area</span>
              </div>
            </div>
          </div>

          {/* Spatial Metadata & Pipeline Card */}
          <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3 shadow-lg">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <span className="text-slate-300 font-bold uppercase">Geospatial Projection & Grid</span>
              <span className="text-[10px] text-emerald-400 font-mono">
                {results.is_georeferenced ? 'EPSG DEFINED' : 'UNREFERENCED'}
              </span>
            </div>

            <div className="space-y-1.5 text-slate-300 text-[11px]">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">CRS:</span>
                <span className="text-cyan-300 font-bold">{image_metadata.crs || 'Unavailable'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Pixel Resolution:</span>
                <span className="text-slate-100">
                  {image_metadata.resolution
                    ? `${image_metadata.resolution[0].toFixed(2)}m × ${image_metadata.resolution[1].toFixed(2)}m`
                    : 'Unavailable'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Model:</span>
                <span className="text-white font-bold">Depth Anything V2 ({results.device_used || 'Unavailable'})</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">DSM Status:</span>
                <span className="text-emerald-400 font-bold">
                  {results.is_georeferenced ? 'Metric DSM (GeoTIFF)' : 'Relative rDSM'}
                </span>
              </div>
              {image_metadata.bounds && (
                <div className="text-[10px] text-slate-400 pt-1 border-t border-slate-800/60">
                  <div>West: {image_metadata.bounds[0].toFixed(1)}</div>
                  <div>South: {image_metadata.bounds[1].toFixed(1)}</div>
                  <div>East: {image_metadata.bounds[2].toFixed(1)}</div>
                  <div>North: {image_metadata.bounds[3].toFixed(1)}</div>
                </div>
              )}
            </div>

            {/* Pipeline Dimensions Matrix */}
            <div className="pt-2 border-t border-slate-800/80 space-y-1 text-[10px]">
              <div className="text-slate-400 uppercase font-bold tracking-wider">Pipeline Resolution Matrix</div>
              <div className="grid grid-cols-2 gap-1.5 pt-1">
                <div className="bg-slate-950/60 p-1.5 rounded border border-slate-800">
                  <span className="text-slate-400">Input: </span>
                  <span className="text-white font-bold">{results.dimensions?.input_width ?? image_metadata.width}×{results.dimensions?.input_height ?? image_metadata.height}</span>
                </div>
                <div className="bg-slate-950/60 p-1.5 rounded border border-slate-800">
                  <span className="text-slate-400">Depth: </span>
                  <span className="text-cyan-300 font-bold">{results.dimensions?.depth_width ?? image_metadata.width}×{results.dimensions?.depth_height ?? image_metadata.height}</span>
                </div>
                <div className="bg-slate-950/60 p-1.5 rounded border border-slate-800">
                  <span className="text-slate-400">DSM: </span>
                  <span className="text-emerald-300 font-bold">{results.dimensions?.dsm_width ?? image_metadata.width}×{results.dimensions?.dsm_height ?? image_metadata.height}</span>
                </div>
                <div className="bg-slate-950/60 p-1.5 rounded border border-slate-800">
                  <span className="text-slate-400">Render: </span>
                  <span className="text-indigo-300 font-bold">{results.dimensions?.render_grid_width ?? results.mesh_metadata.grid_width}×{results.dimensions?.render_grid_height ?? results.mesh_metadata.grid_height}</span>
                </div>
              </div>
              {results.dimensions?.interpolation_applied && (
                <div className="text-amber-300 text-[10px] pt-0.5">
                  Interpolation: {results.dimensions.interpolation_method}
                </div>
              )}
            </div>

            {/* Calibration Details */}
            <div className="pt-2 border-t border-slate-800/80 space-y-1 text-[11px]">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Calibration Method:</span>
                <span className="text-cyan-300 uppercase font-bold">{calibration.method || 'Unavailable'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Calibration MAE:</span>
                <span className="text-white font-bold">
                  {calibration.mae !== undefined && calibration.mae !== null ? `${calibration.mae} m` : 'Unavailable'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Calibration RMSE:</span>
                <span className="text-white font-bold">
                  {calibration.rmse !== undefined && calibration.rmse !== null ? `${calibration.rmse} m` : 'Unavailable'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Correlation / R²:</span>
                <span className="text-emerald-400 font-bold">
                  {calibration.correlation !== undefined && calibration.correlation !== null
                    ? `${calibration.correlation}`
                    : (calibration.r2 !== undefined && calibration.r2 !== null
                      ? `R²: ${calibration.r2}`
                      : 'Unavailable')}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Full-width Hypsometric Elevation Histogram */}
      {histogramData.length > 0 && (
        <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4 shadow-lg font-mono">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center space-x-2">
              <BarChart3 className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                Elevation Hypsometric Histogram (20 Bins)
              </h3>
            </div>
            <div className="flex items-center space-x-3 text-[11px] text-slate-400">
              <span>Relief Range: <strong className="text-white">{dsm_stats.min_elevation} → {dsm_stats.max_elevation} {unit}</strong></span>
              <span>•</span>
              <span>Mean: <strong className="text-cyan-400">{dsm_stats.mean_elevation} {unit}</strong></span>
            </div>
          </div>

          <div className="h-56 w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={histogramData} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
                <XAxis
                  dataKey="bin_label"
                  tick={{ fill: '#64748b', fontSize: 10 }}
                  interval={1}
                  angle={-35}
                  textAnchor="end"
                  height={45}
                />
                <YAxis
                  tick={{ fill: '#64748b', fontSize: 10 }}
                  label={{ value: '% Area', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload;
                      return (
                        <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-xs shadow-xl font-mono">
                          <div className="text-cyan-400 font-bold">Elevation: {data.bin_label}</div>
                          <div className="text-slate-300 mt-1">Area Share: <span className="font-bold text-white">{data.percentage}%</span></div>
                          <div className="text-slate-400 text-[10px]">Pixel Count: {data.count.toLocaleString()}</div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Bar dataKey="percentage" radius={[4, 4, 0, 0]}>
                  {histogramData.map((_, index) => {
                    const ratio = index / Math.max(histogramData.length - 1, 1);
                    const r = Math.round(6 + (245 - 6) * ratio * ratio);
                    const g = Math.round(182 + (158 - 182) * ratio);
                    const b = Math.round(212 + (11 - 212) * ratio);
                    const color = `rgb(${r}, ${g}, ${b})`;
                    return <Cell key={`cell-${index}`} fill={color} />;
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-800/60">
            <span>← Lowest Basins / Valleys</span>
            <span>Terrain Hypsometry: Surface Area Distribution Across Elevation Gradient</span>
            <span>Highest Ridges / Summits →</span>
          </div>
        </div>
      )}
    </div>
  );
};
