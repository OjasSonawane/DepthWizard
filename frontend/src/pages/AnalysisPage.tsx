import React, { useState, useEffect } from 'react';
import { useProject } from '../context/ProjectContext';
import { api } from '../services/api';
import { TerrainProfileResponse } from '../types';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  BarChart,
  Bar
} from 'recharts';
import {
  BarChart2,
  TrendingUp,
  ShieldAlert,
  Activity,
  Cpu,
  Layers,
  Waves,
  ArrowRight
} from 'lucide-react';

export const AnalysisPage: React.FC = () => {
  const { results, currentJobId, setActiveTab } = useProject();

  const [profileData, setProfileData] = useState<TerrainProfileResponse | null>(null);
  const [profileLine, setProfileLine] = useState({
    x1_pct: 0.1,
    y1_pct: 0.2,
    x2_pct: 0.9,
    y2_pct: 0.8
  });
  const [customLine, setCustomLine] = useState({
    x1: 10,
    y1: 20,
    x2: 90,
    y2: 80
  });
  const [loadingProfile, setLoadingProfile] = useState<boolean>(false);
  const [showCustomCoords, setShowCustomCoords] = useState<boolean>(false);

  // Flood simulation state
  const [floodElev, setFloodElev] = useState<number>(0);
  const [floodResult, setFloodResult] = useState<any>(null);
  const [loadingFlood, setLoadingFlood] = useState<boolean>(false);

  // Initialize flood elevation to min_elevation + 20% relief
  useEffect(() => {
    if (results) {
      const initialFlood = results.dsm_stats.min_elevation + results.dsm_stats.relief * 0.2;
      setFloodElev(Math.round(initialFlood * 10) / 10);
    }
  }, [results]);

  // Fetch initial profile
  useEffect(() => {
    if (currentJobId) {
      setLoadingProfile(true);
      api.getTerrainProfile(currentJobId, { ...profileLine, samples: 60 })
        .then(setProfileData)
        .catch(console.error)
        .finally(() => setLoadingProfile(false));
    }
  }, [currentJobId, profileLine]);

  const handleApplyCustomTransect = (e: React.FormEvent) => {
    e.preventDefault();
    const x1_pct = Math.min(Math.max(customLine.x1 / 100, 0), 1);
    const y1_pct = Math.min(Math.max(customLine.y1 / 100, 0), 1);
    const x2_pct = Math.min(Math.max(customLine.x2 / 100, 0), 1);
    const y2_pct = Math.min(Math.max(customLine.y2 / 100, 0), 1);
    setProfileLine({ x1_pct, y1_pct, x2_pct, y2_pct });
  };

  const handleRunFloodSim = () => {
    if (!currentJobId) return;
    setLoadingFlood(true);
    api.simulateFlood(currentJobId, floodElev)
      .then(setFloodResult)
      .catch(console.error)
      .finally(() => setLoadingFlood(false));
  };

  if (!results) {
    return (
      <div className="flex flex-col items-center justify-center h-[70vh] text-center space-y-4">
        <BarChart2 className="w-12 h-12 text-slate-600" />
        <h3 className="text-lg font-bold text-white">No Analysis Data</h3>
        <p className="text-xs text-slate-400 max-w-sm">
          Run an elevation reconstruction to inspect disaster risk indicators and terrain profiles.
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

  const { dsm_stats, disaster_risk, timing_seconds, device_used } = results;
  const unit = dsm_stats.is_metric ? 'm' : 'rel';

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-xl font-bold text-white">Terrain Intelligence & Disaster Analytics</h2>
            <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[10px] font-mono">
              EO-GEOINT
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Topographic vulnerability assessment, slope instability thresholds, and cross-sectional elevation profiling.
          </p>
        </div>

        <button
          onClick={() => setActiveTab('validation')}
          className="flex items-center space-x-2 px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-mono transition-colors self-start sm:self-auto"
        >
          <span>Model Validation →</span>
        </button>
      </div>

      {/* Top Telemetry KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-2">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
            <span>LOW-LYING RISK</span>
            <Waves className="w-4 h-4 text-blue-400" />
          </div>
          <div className="text-2xl font-bold text-blue-400">
            {disaster_risk.low_lying_area_pct}%
          </div>
          <p className="text-[11px] text-slate-400">
            Terrain within bottom 15% relief envelope prone to inundation.
          </p>
        </div>

        <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-2">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
            <span>STEEP SLOPE HAZARD</span>
            <ShieldAlert className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-amber-400">
            {dsm_stats.steep_area_pct}%
          </div>
          <p className="text-[11px] text-slate-400">
            High gradient slopes (&gt;30°) susceptible to mass wasting and rockfalls.
          </p>
        </div>

        <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-2">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
            <span>RUGGEDNESS INDEX</span>
            <Activity className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-emerald-400">
            {disaster_risk.ruggedness_index}
          </div>
          <p className="text-[11px] text-slate-400">
            Laplacian curvature variance across local surface neighborhoods.
          </p>
        </div>

        <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-2">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
            <span>COMPUTE LATENCY</span>
            <Cpu className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold text-cyan-300">
            {timing_seconds.total_seconds !== undefined ? `${timing_seconds.total_seconds}s` : 'Unavailable'}
          </div>
          <p className="text-[11px] text-slate-400 font-mono">
            Hardware acceleration: {device_used}
          </p>
        </div>
      </div>

      {/* Slope Screening Categories Breakdown */}
      <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4 font-mono shadow-xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-2">
            <ShieldAlert className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Slope Instability & Hazard Screening Categories
            </h3>
          </div>
          <div className="text-xs text-slate-400">
            Avg Slope: <strong className="text-white">{dsm_stats.average_slope_deg}°</strong> | Max Slope: <strong className="text-amber-400">{dsm_stats.max_slope_deg}°</strong>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Gentle Slope */}
          <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-emerald-400 font-bold">&lt; 15° GENTLE SLOPE</span>
              <span className="text-base font-bold text-emerald-300">{disaster_risk.gentle_slope_pct}%</span>
            </div>
            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
              <div
                className="bg-emerald-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${disaster_risk.gentle_slope_pct}%` }}
              />
            </div>
            <p className="text-[11px] text-slate-400 font-sans">
              Low gravitational hazard. Stable ground suitable for emergency access routes and transit staging.
            </p>
          </div>

          {/* Moderate Slope */}
          <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-amber-400 font-bold">15° – 30° MODERATE</span>
              <span className="text-base font-bold text-amber-300">{disaster_risk.moderate_slope_pct}%</span>
            </div>
            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
              <div
                className="bg-amber-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${disaster_risk.moderate_slope_pct}%` }}
              />
            </div>
            <p className="text-[11px] text-slate-400 font-sans">
              Intermediate slope. Subject to sheet erosion, enhanced surface runoff, and moderate soil creep.
            </p>
          </div>

          {/* Steep Slope */}
          <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-rose-400 font-bold">&gt; 30° STEEP HAZARD</span>
              <span className="text-base font-bold text-rose-300">{disaster_risk.steep_slope_hazard_pct}%</span>
            </div>
            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
              <div
                className="bg-rose-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${disaster_risk.steep_slope_hazard_pct}%` }}
              />
            </div>
            <p className="text-[11px] text-slate-400 font-sans">
              Critical instability envelope. High hazard for slope failure, rockfalls, and debris flow during rainfall.
            </p>
          </div>
        </div>
      </div>

      {/* Interactive Terrain Elevation Profile Section */}
      <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-6 shadow-xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-base font-bold text-white flex items-center space-x-2">
              <TrendingUp className="w-4 h-4 text-cyan-400" />
              <span>Interactive Cross-Sectional Elevation Profile</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Continuous topographical transect sampled along user-defined trajectory.
            </p>
          </div>

          {/* Quick Preset Transects & Custom Toggle */}
          <div className="flex items-center space-x-2 text-xs font-mono">
            <span className="text-slate-400">Presets:</span>
            <button
              onClick={() => {
                setShowCustomCoords(false);
                setProfileLine({ x1_pct: 0.1, y1_pct: 0.2, x2_pct: 0.9, y2_pct: 0.8 });
              }}
              className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
            >
              Diagonal
            </button>
            <button
              onClick={() => {
                setShowCustomCoords(false);
                setProfileLine({ x1_pct: 0.1, y1_pct: 0.5, x2_pct: 0.9, y2_pct: 0.5 });
              }}
              className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
            >
              W-E
            </button>
            <button
              onClick={() => {
                setShowCustomCoords(false);
                setProfileLine({ x1_pct: 0.5, y1_pct: 0.1, x2_pct: 0.5, y2_pct: 0.9 });
              }}
              className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
            >
              N-S
            </button>
            <button
              onClick={() => setShowCustomCoords(!showCustomCoords)}
              className={`px-2.5 py-1 rounded border transition-colors ${
                showCustomCoords
                  ? 'bg-cyan-500 text-black font-bold border-cyan-400'
                  : 'bg-slate-800 text-cyan-400 border-slate-700 hover:bg-slate-700'
              }`}
            >
              Custom Coords
            </button>
          </div>
        </div>

        {/* Custom Coordinates Inputs Form */}
        {showCustomCoords && (
          <form
            onSubmit={handleApplyCustomTransect}
            className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 grid grid-cols-2 sm:grid-cols-5 gap-3 items-end font-mono text-xs"
          >
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">Start X (%)</label>
              <input
                type="number"
                min="0"
                max="100"
                value={customLine.x1}
                onChange={(e) => setCustomLine({ ...customLine, x1: Number(e.target.value) })}
                className="w-full px-2.5 py-1.5 rounded bg-slate-900 border border-slate-700 text-white focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">Start Y (%)</label>
              <input
                type="number"
                min="0"
                max="100"
                value={customLine.y1}
                onChange={(e) => setCustomLine({ ...customLine, y1: Number(e.target.value) })}
                className="w-full px-2.5 py-1.5 rounded bg-slate-900 border border-slate-700 text-white focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">End X (%)</label>
              <input
                type="number"
                min="0"
                max="100"
                value={customLine.x2}
                onChange={(e) => setCustomLine({ ...customLine, x2: Number(e.target.value) })}
                className="w-full px-2.5 py-1.5 rounded bg-slate-900 border border-slate-700 text-white focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">End Y (%)</label>
              <input
                type="number"
                min="0"
                max="100"
                value={customLine.y2}
                onChange={(e) => setCustomLine({ ...customLine, y2: Number(e.target.value) })}
                className="w-full px-2.5 py-1.5 rounded bg-slate-900 border border-slate-700 text-white focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div className="col-span-2 sm:col-span-1">
              <button
                type="submit"
                className="w-full py-1.5 rounded bg-cyan-500 hover:bg-cyan-400 text-black font-bold transition-colors"
              >
                Sample
              </button>
            </div>
          </form>
        )}

        {/* Profile Chart Canvas */}
        <div className="h-72 w-full">
          {profileData ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={profileData.points} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="elevGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#00f0ff" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#00f0ff" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                  dataKey="distance_m"
                  stroke="#64748b"
                  tick={{ fill: '#94a3b8', fontSize: 11, fontFamily: 'JetBrains Mono' }}
                  tickFormatter={(val) => `${val}m`}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fill: '#94a3b8', fontSize: 11, fontFamily: 'JetBrains Mono' }}
                  tickFormatter={(val) => `${val}${unit}`}
                  domain={['auto', 'auto']}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload;
                      return (
                        <div className="bg-slate-900 border border-slate-700 p-3 rounded-lg shadow-xl font-mono text-xs space-y-1">
                          <div className="text-slate-400">Distance: <span className="text-white font-bold">{data.distance_m}m</span></div>
                          <div className="text-cyan-400 font-bold">Elevation: {data.elevation} {unit}</div>
                          <div className="text-amber-400">Local Slope: {data.slope_deg}°</div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="elevation"
                  stroke="#00f0ff"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#elevGrad)"
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-xs font-mono text-slate-500">
              {loadingProfile ? 'Sampling transect profile...' : 'Loading transect profile data...'}
            </div>
          )}
        </div>

        {/* Profile Metrics summary */}
        {profileData && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-3 border-t border-slate-800 text-xs font-mono">
            <div>
              <span className="text-slate-400">Total Transect Length:</span>
              <div className="text-white font-bold text-sm mt-0.5">{profileData.total_distance_m}m</div>
            </div>
            <div>
              <span className="text-slate-400">Min / Max Elevation:</span>
              <div className="text-cyan-300 font-bold text-sm mt-0.5">
                {profileData.min_elevation} / {profileData.max_elevation} {unit}
              </div>
            </div>
            <div>
              <span className="text-slate-400">Cumulative Elevation Gain:</span>
              <div className="text-emerald-400 font-bold text-sm mt-0.5">+{profileData.elevation_gain_m}m</div>
            </div>
            <div>
              <span className="text-slate-400">Cumulative Elevation Loss:</span>
              <div className="text-rose-400 font-bold text-sm mt-0.5">-{profileData.elevation_loss_m}m</div>
            </div>
          </div>
        )}
      </div>

      {/* Flood Inundation Threshold Simulator */}
      <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4 font-mono shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-2">
            <Waves className="w-4 h-4 text-blue-400" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Hydrological Inundation Threshold Simulator
            </h3>
          </div>
          <span className="text-[10px] text-blue-400 border border-blue-500/20 px-2 py-0.5 rounded bg-blue-500/10">
            THRESHOLD MODEL
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-center">
          <div className="md:col-span-6 space-y-3">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400">Simulated Water Elevation:</span>
              <span className="text-blue-300 font-bold text-sm">{floodElev} {unit}</span>
            </div>
            <input
              type="range"
              min={dsm_stats.min_elevation}
              max={dsm_stats.max_elevation}
              step={0.5}
              value={floodElev}
              onChange={(e) => setFloodElev(Number(e.target.value))}
              className="w-full accent-blue-400 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-slate-500">
              <span>Min: {dsm_stats.min_elevation} {unit}</span>
              <span>Max: {dsm_stats.max_elevation} {unit}</span>
            </div>
            <button
              onClick={handleRunFloodSim}
              disabled={loadingFlood}
              className="px-4 py-2 rounded-lg bg-blue-500 hover:bg-blue-400 text-white font-bold text-xs transition-colors shadow-md shadow-blue-500/20"
            >
              {loadingFlood ? 'Calculating Inundation...' : 'Run Inundation Analysis'}
            </button>
          </div>

          <div className="md:col-span-6 p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-3 text-xs">
            {floodResult ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Inundated Area Share:</span>
                  <span className="text-blue-400 font-bold text-base">{floodResult.inundated_area_pct}%</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Flooded Surface:</span>
                  <span className="text-white font-bold">{floodResult.inundated_area_sq_m ? `${(floodResult.inundated_area_sq_m / 10000).toFixed(1)} ha` : 'Relative cells'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Mean Water Depth:</span>
                  <span className="text-cyan-300 font-bold">{floodResult.mean_water_depth_m.toFixed(2)} {unit}</span>
                </div>
                <p className="text-[10px] text-slate-500 pt-1 border-t border-slate-800">
                  Calculated by thresholding DSM cells below the target water elevation plane.
                </p>
              </div>
            ) : (
              <div className="text-slate-500 text-center py-4">
                Adjust the elevation slider and click "Run Inundation Analysis" to compute affected surface percentage.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Performance & Execution Specs */}
      <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-3 font-mono text-xs">
        <h4 className="font-bold text-slate-300 uppercase tracking-wider">
          Reconstruction Pipeline Execution Timings
        </h4>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-slate-300 pt-2">
          <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
            <span className="text-[10px] text-slate-400">PREPROCESSING</span>
            <div className="text-sm font-bold text-white mt-0.5">
              {timing_seconds.preprocessing !== undefined ? `${timing_seconds.preprocessing}s` : 'Unavailable'}
            </div>
          </div>
          <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
            <span className="text-[10px] text-slate-400">DEPTH INFERENCE</span>
            <div className="text-sm font-bold text-cyan-400 mt-0.5">
              {timing_seconds.inference !== undefined ? `${timing_seconds.inference}s` : 'Unavailable'}
            </div>
          </div>
          <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
            <span className="text-[10px] text-slate-400">SCALE CALIBRATION</span>
            <div className="text-sm font-bold text-indigo-400 mt-0.5">
              {timing_seconds.calibration !== undefined ? `${timing_seconds.calibration}s` : 'Unavailable'}
            </div>
          </div>
          <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
            <span className="text-[10px] text-slate-400">3D MESH GENERATION</span>
            <div className="text-sm font-bold text-emerald-400 mt-0.5">
              {timing_seconds.mesh_generation !== undefined ? `${timing_seconds.mesh_generation}s` : 'Unavailable'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
