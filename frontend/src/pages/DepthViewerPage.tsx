import React, { useState } from 'react';
import { useProject } from '../context/ProjectContext';
import { Layers, Info, Download, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';

export const DepthViewerPage: React.FC = () => {
  const { results, setActiveTab } = useProject();
  const [viewMode, setViewMode] = useState<'color' | 'gray' | 'rgb' | 'side_by_side'>('color');
  const [sliderPos, setSliderPos] = useState<number>(50);
  const [zoomLevel, setZoomLevel] = useState<number>(1.0);
  const [opacity, setOpacity] = useState<number>(100);

  if (!results) {
    return (
      <div className="flex flex-col items-center justify-center h-[70vh] text-center space-y-4">
        <Layers className="w-12 h-12 text-slate-600" />
        <h3 className="text-lg font-bold text-white">No Reconstruction Active</h3>
        <p className="text-xs text-slate-400 max-w-sm">
          Upload an image or load an ISRO sample dataset to generate the relative depth map.
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

  const getImageSrc = () => {
    switch (viewMode) {
      case 'gray':
        return results.assets.depth_gray;
      case 'rgb':
        return results.assets.rgb_texture;
      case 'color':
      default:
        return results.assets.depth_color;
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-xl font-bold text-white">Monocular Depth & Relative Elevation</h2>
            <span className="px-2.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[10px] font-mono font-bold">
              RELATIVE DEPTH (UNITLESS)
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Scene geometry inferred via neural vision transformer. Values represent scale-agnostic inverse depth / relative elevation surface.
          </p>
        </div>

        {/* View mode tabs */}
        <div className="flex items-center space-x-1.5 bg-slate-900/80 p-1 rounded-xl border border-slate-800 text-xs font-mono">
          <button
            onClick={() => setViewMode('color')}
            className={`px-3 py-1.5 rounded-lg transition-all ${
              viewMode === 'color' ? 'bg-cyan-500 text-black font-bold' : 'text-slate-400 hover:text-white'
            }`}
          >
            Colorized Depth
          </button>
          <button
            onClick={() => setViewMode('gray')}
            className={`px-3 py-1.5 rounded-lg transition-all ${
              viewMode === 'gray' ? 'bg-cyan-500 text-black font-bold' : 'text-slate-400 hover:text-white'
            }`}
          >
            Grayscale
          </button>
          <button
            onClick={() => setViewMode('rgb')}
            className={`px-3 py-1.5 rounded-lg transition-all ${
              viewMode === 'rgb' ? 'bg-cyan-500 text-black font-bold' : 'text-slate-400 hover:text-white'
            }`}
          >
            Original Optical RGB
          </button>
          <button
            onClick={() => setViewMode('side_by_side')}
            className={`px-3 py-1.5 rounded-lg transition-all ${
              viewMode === 'side_by_side' ? 'bg-cyan-500 text-black font-bold' : 'text-slate-400 hover:text-white'
            }`}
          >
            Split Swipe
          </button>
        </div>
      </div>

      {/* Main Viewer Area */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Image Canvas / Comparison */}
        <div className="lg:col-span-8 space-y-3">
          <div className="relative rounded-2xl bg-slate-950 border border-slate-800 overflow-hidden aspect-square max-h-[580px] flex items-center justify-center shadow-2xl">
            {viewMode === 'side_by_side' ? (
              <div className="relative w-full h-full select-none overflow-hidden" style={{ transform: `scale(${zoomLevel})` }}>
                {/* Background: Original RGB */}
                <img
                  src={results.assets.rgb_texture}
                  alt="Original Satellite RGB"
                  className="absolute inset-0 w-full h-full object-contain"
                />
                {/* Foreground: Depth Map clipped by slider */}
                <div
                  className="absolute inset-0 overflow-hidden"
                  style={{ width: `${sliderPos}%` }}
                >
                  <img
                    src={results.assets.depth_color}
                    alt="Depth Surface"
                    className="absolute inset-0 w-full h-full object-contain max-w-none"
                    style={{ width: '100%', height: '100%', opacity: opacity / 100 }}
                  />
                </div>
                {/* Vertical Divider line */}
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-cyan-400 shadow-[0_0_10px_#00f0ff]"
                  style={{ left: `${sliderPos}%` }}
                >
                  <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-6 h-6 rounded-full bg-cyan-500 text-black flex items-center justify-center text-[10px] font-bold shadow-lg">
                    ⇄
                  </div>
                </div>
              </div>
            ) : (
              <div className="w-full h-full flex items-center justify-center overflow-hidden">
                <img
                  src={getImageSrc()}
                  alt="Depth Map"
                  className="w-full h-full object-contain transition-transform duration-150"
                  style={{ transform: `scale(${zoomLevel})`, opacity: opacity / 100 }}
                />
              </div>
            )}

            {/* Scientific watermark / badge */}
            <div className="absolute bottom-3 left-3 px-3 py-1.5 rounded-lg bg-black/80 backdrop-blur-md border border-slate-800 text-[11px] font-mono text-slate-300">
              {viewMode === 'side_by_side'
                ? `RGB (Right) ⟷ Relative Depth (Left: ${sliderPos}%)`
                : viewMode === 'color'
                ? 'Relative Elevation Surface [0.0 → 1.0]'
                : viewMode === 'gray'
                ? 'Grayscale Relative Disparity [0 → 255]'
                : 'Original Satellite Sensor Image'}
            </div>

            {/* Zoom Controls Overlay */}
            <div className="absolute top-3 right-3 flex items-center space-x-1 bg-slate-900/80 backdrop-blur-md p-1 rounded-lg border border-slate-800 text-slate-400">
              <button
                onClick={() => setZoomLevel(Math.min(zoomLevel + 0.25, 3.0))}
                className="p-1.5 hover:text-white hover:bg-slate-800 rounded transition-colors"
                title="Zoom In"
              >
                <ZoomIn className="w-4 h-4" />
              </button>
              <button
                onClick={() => setZoomLevel(Math.max(zoomLevel - 0.25, 0.75))}
                className="p-1.5 hover:text-white hover:bg-slate-800 rounded transition-colors"
                title="Zoom Out"
              >
                <ZoomOut className="w-4 h-4" />
              </button>
              <button
                onClick={() => setZoomLevel(1.0)}
                className="p-1.5 hover:text-white hover:bg-slate-800 rounded transition-colors"
                title="Reset Zoom"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Slider for split comparison and opacity */}
          <div className="p-3.5 rounded-xl bg-slate-900/70 border border-slate-800 flex flex-wrap items-center justify-between gap-4 text-xs font-mono">
            {viewMode === 'side_by_side' && (
              <div className="flex items-center space-x-3 flex-1 min-w-[200px]">
                <span className="text-slate-400">SPLIT SWIPE:</span>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={sliderPos}
                  onChange={(e) => setSliderPos(Number(e.target.value))}
                  className="flex-1 accent-cyan-400 cursor-pointer"
                />
                <span className="text-cyan-300 w-10 text-right">{sliderPos}%</span>
              </div>
            )}

            <div className="flex items-center space-x-3">
              <span className="text-slate-400">OPACITY:</span>
              <input
                type="range"
                min="20"
                max="100"
                value={opacity}
                onChange={(e) => setOpacity(Number(e.target.value))}
                className="w-24 accent-cyan-400 cursor-pointer"
              />
              <span className="text-cyan-300 w-8">{opacity}%</span>
            </div>

            <div className="text-[11px] text-slate-400">
              Zoom: <span className="text-white font-bold">{Math.round(zoomLevel * 100)}%</span>
            </div>
          </div>
        </div>

        {/* Right: Technical Telemetry & Calibration Details */}
        <div className="lg:col-span-4 space-y-4">
          <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4 font-mono text-xs shadow-lg">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <span className="text-cyan-400 font-bold uppercase">RELATIVE DEPTH METRICS</span>
              <span className="text-slate-400 text-[10px]">{results.device_used}</span>
            </div>

            <div className="space-y-2 text-slate-300">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Inference Time:</span>
                <span className="text-white font-bold">
                  {results.timing_seconds.inference !== undefined ? `${results.timing_seconds.inference}s` : 'Unavailable'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Array Type:</span>
                <span className="text-slate-200">Float32 [0.0 .. 1.0]</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Min Relative Depth:</span>
                <span className="text-slate-200">0.00 (Far/Low)</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Max Relative Depth:</span>
                <span className="text-slate-200">1.00 (Near/High)</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Colormap:</span>
                <span className="text-slate-200">Perceptually Uniform Turbo</span>
              </div>
            </div>

            {/* Pipeline Resolution Breakdown */}
            <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
              <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                Pipeline Resolution Stages
              </div>
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="bg-slate-900/60 p-2 rounded border border-slate-800">
                  <div className="text-slate-400 text-[10px]">Input Image:</div>
                  <div className="font-bold text-white">
                    {results.dimensions?.input_width ?? results.image_metadata.width} × {results.dimensions?.input_height ?? results.image_metadata.height}
                  </div>
                </div>
                <div className="bg-slate-900/60 p-2 rounded border border-slate-800">
                  <div className="text-slate-400 text-[10px]">Depth Tensor:</div>
                  <div className="font-bold text-cyan-300">
                    {results.dimensions?.depth_width ?? results.image_metadata.width} × {results.dimensions?.depth_height ?? results.image_metadata.height}
                  </div>
                </div>
                <div className="bg-slate-900/60 p-2 rounded border border-slate-800">
                  <div className="text-slate-400 text-[10px]">DSM Surface:</div>
                  <div className="font-bold text-emerald-300">
                    {results.dimensions?.dsm_width ?? results.image_metadata.width} × {results.dimensions?.dsm_height ?? results.image_metadata.height}
                  </div>
                </div>
                <div className="bg-slate-900/60 p-2 rounded border border-slate-800">
                  <div className="text-slate-400 text-[10px]">Render Mesh Grid:</div>
                  <div className="font-bold text-indigo-300">
                    {results.dimensions?.render_grid_width ?? results.mesh_metadata.grid_width} × {results.dimensions?.render_grid_height ?? results.mesh_metadata.grid_height}
                  </div>
                </div>
              </div>
              {results.dimensions?.interpolation_applied && (
                <div className="text-[10px] text-amber-300 pt-1">
                  • Resampled via {results.dimensions.interpolation_method} interpolation for continuous 3D surface
                </div>
              )}
            </div>

            {/* Scientific Explanation Notice (Required by Phase 6) */}
            <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-[11px] space-y-1.5">
              <div className="flex items-center space-x-1.5 text-amber-400 font-bold">
                <Info className="w-4 h-4 flex-shrink-0" />
                <span>SCIENTIFIC INTEGRITY NOTICE</span>
              </div>
              <p className="text-slate-300 leading-relaxed text-[11px]">
                Monocular depth provides scale-agnostic scene geometry. Metric elevation requires calibration.
                Relative depth values are normalized into unitless range [0.0, 1.0] and are NOT meters.
              </p>
            </div>

            {/* Quick Actions */}
            <div className="pt-2 border-t border-slate-800 space-y-2">
              <a
                href={results.assets.depth_color}
                download
                className="w-full py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-center block text-[11px] font-sans transition-colors"
              >
                Download Depth Map PNG
              </a>

              <button
                onClick={() => setActiveTab('dsm')}
                className="w-full py-2 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 text-cyan-300 border border-cyan-500/30 text-center block text-[11px] font-sans transition-colors"
              >
                Proceed to Surface Model (DSM) →
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
