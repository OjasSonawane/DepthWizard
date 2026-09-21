import React, { useState, useEffect } from 'react';
import { useProject } from '../context/ProjectContext';
import { api } from '../services/api';
import { EvaluationMetrics, PointInspectionResult } from '../types';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ScatterChart,
  Scatter,
  ReferenceLine
} from 'recharts';
import {
  CheckCircle2,
  AlertCircle,
  UploadCloud,
  FileCheck,
  Layers,
  TrendingDown,
  Info,
  SlidersHorizontal,
  Settings2,
  ShieldCheck,
  Check,
  RefreshCw,
  Download,
  MousePointerClick,
  Crosshair
} from 'lucide-react';

interface MetricDef {
  key: string;
  name: string;
  category: 'elevation' | 'depth' | 'slope';
  unit: string;
  direction: 'lower' | 'zero' | 'one' | 'higher';
  directionLabel: string;
  description: string;
  getValue: (m: EvaluationMetrics) => number | null | undefined;
  format: (v: number) => string;
}

const ALL_METRICS: MetricDef[] = [
  // Elevation Metrics
  {
    key: 'mae',
    name: 'Mean Absolute Error (MAE)',
    category: 'elevation',
    unit: 'm',
    direction: 'lower',
    directionLabel: 'Lower is better',
    description: 'Average magnitude of vertical elevation errors across all valid overlapping pixels.',
    getValue: (m) => m.mae,
    format: (v) => `${v.toFixed(2)}m`
  },
  {
    key: 'rmse',
    name: 'Root Mean Squared Error (RMSE)',
    category: 'elevation',
    unit: 'm',
    direction: 'lower',
    directionLabel: 'Lower is better',
    description: 'Standard deviation of vertical residuals. Heavily penalizes large relief deviations and outliers.',
    getValue: (m) => m.rmse,
    format: (v) => `${v.toFixed(2)}m`
  },
  {
    key: 'pearson_r',
    name: 'Pearson Correlation (r)',
    category: 'elevation',
    unit: '',
    direction: 'one',
    directionLabel: 'Closer to 1 is better',
    description: 'Measures topographic shape and slope pattern agreement [-1 to +1] with ground truth.',
    getValue: (m) => m.pearson_r,
    format: (v) => v.toFixed(3)
  },
  {
    key: 'r2',
    name: 'Coefficient of Determination (R²)',
    category: 'elevation',
    unit: '',
    direction: 'one',
    directionLabel: 'Closer to 1 is better',
    description: 'Proportion of ground truth elevation variance accounted for by the reconstructed model.',
    getValue: (m) => m.r2,
    format: (v) => v.toFixed(3)
  },
  {
    key: 'mbe',
    name: 'Mean Bias Error (MBE)',
    category: 'elevation',
    unit: 'm',
    direction: 'zero',
    directionLabel: 'Closer to 0 is better',
    description: 'Systematic vertical offset. Positive indicates overestimation; negative indicates underestimation.',
    getValue: (m) => m.mbe,
    format: (v) => (v > 0 ? `+${v.toFixed(2)}m` : `${v.toFixed(2)}m`)
  },
  {
    key: 'median_abs_error',
    name: 'Median Absolute Error',
    category: 'elevation',
    unit: 'm',
    direction: 'lower',
    directionLabel: 'Lower is better',
    description: 'Median absolute vertical error, resilient against extreme localized spikes and noise.',
    getValue: (m) => m.median_abs_error ?? m.median_error,
    format: (v) => `${v.toFixed(2)}m`
  },
  {
    key: 'max_abs_error',
    name: 'Maximum Absolute Error',
    category: 'elevation',
    unit: 'm',
    direction: 'lower',
    directionLabel: 'Lower is better',
    description: 'Worst-case vertical error detected across the entire overlapping validation area.',
    getValue: (m) => m.max_abs_error,
    format: (v) => `${v.toFixed(2)}m`
  },
  {
    key: 'le90',
    name: 'Linear Error 90% (LE90)',
    category: 'elevation',
    unit: 'm',
    direction: 'lower',
    directionLabel: 'Lower is better',
    description: '90th percentile vertical error. Standard USGS / FGDC geospatial vertical accuracy metric.',
    getValue: (m) => m.le90,
    format: (v) => `${v.toFixed(2)}m`
  },
  {
    key: 'le95',
    name: 'Linear Error 95% (LE95)',
    category: 'elevation',
    unit: 'm',
    direction: 'lower',
    directionLabel: 'Lower is better',
    description: '95th percentile vertical error. Stricter geospatial standard for critical engineering tasks.',
    getValue: (m) => m.le95,
    format: (v) => `${v.toFixed(2)}m`
  },
  {
    key: 'valid_pixel_pct',
    name: 'Valid Evaluated Pixels',
    category: 'elevation',
    unit: '%',
    direction: 'higher',
    directionLabel: 'Higher is better',
    description: 'Spatial overlap percentage of finite non-nodata pixels between reconstructed DSM and reference.',
    getValue: (m) => m.valid_pixel_pct,
    format: (v) => `${v.toFixed(1)}%`
  },
  // Monocular Depth Benchmark Metrics
  {
    key: 'abs_rel',
    name: 'Mean Absolute Relative Error (AbsRel)',
    category: 'depth',
    unit: '',
    direction: 'lower',
    directionLabel: 'Lower is better',
    description: 'Standard benchmark metric: 1/N * sum(|d - d*| / d*) across positive reference values.',
    getValue: (m) => m.abs_rel,
    format: (v) => v.toFixed(4)
  },
  {
    key: 'sq_rel',
    name: 'Squared Relative Error (SqRel)',
    category: 'depth',
    unit: '',
    direction: 'lower',
    directionLabel: 'Lower is better',
    description: 'Squared relative vertical error: 1/N * sum((d - d*)^2 / d*).',
    getValue: (m) => m.sq_rel,
    format: (v) => v.toFixed(4)
  },
  {
    key: 'delta1',
    name: 'Accuracy Threshold δ < 1.25',
    category: 'depth',
    unit: '%',
    direction: 'higher',
    directionLabel: 'Higher is better',
    description: 'Percentage of points where max(pred/ref, ref/pred) < 1.25. Benchmark standard.',
    getValue: (m) => m.delta1,
    format: (v) => `${v.toFixed(1)}%`
  },
  {
    key: 'delta2',
    name: 'Accuracy Threshold δ < 1.25²',
    category: 'depth',
    unit: '%',
    direction: 'higher',
    directionLabel: 'Higher is better',
    description: 'Percentage of points where ratio < 1.5625 (1.25 squared).',
    getValue: (m) => m.delta2,
    format: (v) => `${v.toFixed(1)}%`
  },
  {
    key: 'delta3',
    name: 'Accuracy Threshold δ < 1.25³',
    category: 'depth',
    unit: '%',
    direction: 'higher',
    directionLabel: 'Higher is better',
    description: 'Percentage of points where ratio < 1.9531 (1.25 cubed).',
    getValue: (m) => m.delta3,
    format: (v) => `${v.toFixed(1)}%`
  },
  // Terrain Slope Metrics
  {
    key: 'slope_mae',
    name: 'Slope Gradient MAE',
    category: 'slope',
    unit: '°',
    direction: 'lower',
    directionLabel: 'Lower is better',
    description: 'Mean absolute error of surface slope gradients in degrees computed via Horn 3×3 kernels.',
    getValue: (m) => m.slope_mae,
    format: (v) => `${v.toFixed(2)}°`
  },
  {
    key: 'slope_rmse',
    name: 'Slope Gradient RMSE',
    category: 'slope',
    unit: '°',
    direction: 'lower',
    directionLabel: 'Lower is better',
    description: 'Root mean square error of surface slope in degrees, verifying terrain incline fidelity.',
    getValue: (m) => m.slope_rmse,
    format: (v) => `${v.toFixed(2)}°`
  }
];

const PRESET_PROFILES = [
  {
    id: 'terrain_standard',
    name: 'Terrain Standard',
    desc: 'Core elevation metrics + R² and valid pixel coverage',
    metrics: ['mae', 'rmse', 'pearson_r', 'mbe', 'median_abs_error', 'max_abs_error', 'r2', 'valid_pixel_pct']
  },
  {
    id: 'terrain_basic',
    name: 'Basic Terrain',
    desc: 'Standard minimal set: MAE, RMSE, Pearson r, MBE',
    metrics: ['mae', 'rmse', 'pearson_r', 'mbe']
  },
  {
    id: 'terrain_comprehensive',
    name: 'Terrain Comprehensive',
    desc: 'All elevation + FGDC LE90/LE95 + Horn slope gradients',
    metrics: [
      'mae', 'rmse', 'pearson_r', 'mbe', 'median_abs_error', 'max_abs_error',
      'r2', 'valid_pixel_pct', 'le90', 'le95', 'slope_mae', 'slope_rmse'
    ]
  },
  {
    id: 'depth_benchmark',
    name: 'Depth Benchmark',
    desc: 'Monocular depth metrics (AbsRel, SqRel, δ thresholds)',
    metrics: ['abs_rel', 'sq_rel', 'delta1', 'delta2', 'delta3', 'rmse', 'mae']
  },
  {
    id: 'custom',
    name: 'Custom Profile',
    desc: 'Tailored user selection across all 17 scientific metrics',
    metrics: []
  }
];

export const ValidationPage: React.FC = () => {
  const { results, currentJobId, evaluation, setEvaluation, setActiveTab } = useProject();
  const [refFile, setRefFile] = useState<File | null>(null);
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);
  const [isReconfiguring, setIsReconfiguring] = useState<boolean>(false);
  const [evalError, setEvalError] = useState<string | null>(null);

  // Configuration state
  const [activeProfile, setActiveProfile] = useState<string>('terrain_standard');
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([
    'mae', 'rmse', 'pearson_r', 'mbe', 'median_abs_error', 'max_abs_error', 'r2', 'valid_pixel_pct'
  ]);
  const [showConfigDrawer, setShowConfigDrawer] = useState<boolean>(false);

  // Layer state for error map
  const [activeLayer, setActiveLayer] = useState<'signed_error' | 'abs_error' | 'predicted' | 'reference' | 'hillshade'>('signed_error');

  // Interactive Pixel Inspection State (only active when reference data exists)
  const [clickMarker, setClickMarker] = useState<{ xPct: number; yPct: number } | null>(null);
  const [inspectedPoint, setInspectedPoint] = useState<PointInspectionResult | null>(null);
  const [isInspecting, setIsInspecting] = useState<boolean>(false);

  // Sync state from existing evaluation if loaded
  useEffect(() => {
    if (evaluation?.profile_name) {
      setActiveProfile(evaluation.profile_name);
    }
    if (evaluation?.selected_metrics && evaluation.selected_metrics.length > 0) {
      setSelectedMetrics(evaluation.selected_metrics);
    }
  }, [evaluation?.profile_name, evaluation?.selected_metrics]);

  if (!results || !currentJobId) {
    return (
      <div className="flex flex-col items-center justify-center h-[70vh] text-center space-y-4">
        <CheckCircle2 className="w-12 h-12 text-slate-600" />
        <h3 className="text-lg font-bold text-white">No Surface Model Active</h3>
        <p className="text-xs text-slate-400 max-w-sm">
          Run an elevation reconstruction before validating against reference datasets.
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

  const hasEval = Boolean(evaluation && evaluation.has_evaluation && evaluation.metrics);

  // Handle uploading ground truth reference DEM
  const handleUploadAndEvaluate = async () => {
    if (!refFile) return;
    setIsEvaluating(true);
    setEvalError(null);
    try {
      const evalResp = await api.evaluateDSM(currentJobId, refFile, {
        profile: activeProfile,
        selectedMetrics: activeProfile === 'custom' ? selectedMetrics : undefined
      });
      setEvaluation(evalResp);
      setIsEvaluating(false);
    } catch (e: any) {
      setEvalError(e.message || 'Validation evaluation failed');
      setIsEvaluating(false);
    }
  };

  // Handle profile preset selection
  const handleSelectProfile = async (profileId: string) => {
    setActiveProfile(profileId);
    const preset = PRESET_PROFILES.find((p) => p.id === profileId);
    let newMetrics = selectedMetrics;
    if (preset && preset.id !== 'custom') {
      newMetrics = preset.metrics;
      setSelectedMetrics(newMetrics);
    }

    // If existing evaluation is present, reconfigure on the backend instantly
    if (hasEval) {
      setIsReconfiguring(true);
      try {
        const resp = await api.configureEvaluation(currentJobId, {
          profile: profileId,
          selectedMetrics: profileId === 'custom' ? newMetrics : undefined
        });
        setEvaluation(resp);
      } catch (err: any) {
        console.error('Failed to reconfigure evaluation profile:', err);
      } finally {
        setIsReconfiguring(false);
      }
    }
  };

  // Toggle individual metric in custom mode
  const handleToggleMetric = async (metricKey: string) => {
    let updated: string[];
    if (selectedMetrics.includes(metricKey)) {
      updated = selectedMetrics.filter((k) => k !== metricKey);
    } else {
      updated = [...selectedMetrics, metricKey];
    }
    setSelectedMetrics(updated);
    setActiveProfile('custom');

    if (hasEval) {
      setIsReconfiguring(true);
      try {
        const resp = await api.configureEvaluation(currentJobId, {
          profile: 'custom',
          selectedMetrics: updated
        });
        setEvaluation(resp);
      } catch (err: any) {
        console.error('Failed to update metric configuration:', err);
      } finally {
        setIsReconfiguring(false);
      }
    }
  };

  const getActiveLayerImage = () => {
    if (!hasEval || !evaluation) return '';
    switch (activeLayer) {
      case 'abs_error':
        return evaluation.abs_error_map_url || evaluation.error_map_url || '';
      case 'predicted':
        return evaluation.predicted_map_url || results.assets.dsm_color;
      case 'reference':
        return evaluation.reference_map_url || '';
      case 'hillshade':
        return results.assets.hillshade;
      case 'signed_error':
      default:
        return evaluation.error_map_url || '';
    }
  };

  const handleMapClick = async (e: React.MouseEvent<HTMLDivElement>) => {
    if (!hasEval || !currentJobId) return;
    const rect = e.currentTarget.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const xPct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const yPct = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));

    setClickMarker({ xPct, yPct });
    setIsInspecting(true);
    try {
      const data = await api.inspectPoint(currentJobId, { x_pct: xPct, y_pct: yPct });
      setInspectedPoint(data);
    } catch (err: any) {
      console.error('Failed to inspect point on validation map:', err);
    } finally {
      setIsInspecting(false);
    }
  };

  // Filter metrics to display based on selectedMetrics
  const displayMetrics = ALL_METRICS.filter(
    (m) => selectedMetrics.includes(m.key) && evaluation?.metrics && m.getValue(evaluation.metrics) !== null && m.getValue(evaluation.metrics) !== undefined
  );

  // Min and max bounds for scatter plot reference 1:1 line
  const scatterMin = evaluation?.metrics ? Math.floor(Math.min(evaluation.metrics.reference_min, evaluation.metrics.predicted_min)) : 0;
  const scatterMax = evaluation?.metrics ? Math.ceil(Math.max(evaluation.metrics.reference_max, evaluation.metrics.predicted_max)) : 100;

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <h2 className="text-xl font-bold text-white tracking-tight">Model Validation & Accuracy Benchmarking</h2>
            <span className="px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 text-[10px] font-mono font-bold">
              SCIENTIFIC EVALUATION
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Configurable validation against reference elevation (DEM / LiDAR). Standardized FGDC LE90/LE95, Horn slope, and monocular depth metrics.
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <label className="cursor-pointer">
            <input
              type="file"
              accept=".tif,.tiff,.npy"
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.[0]) setRefFile(e.target.files[0]);
              }}
            />
            <span className="flex items-center space-x-2 px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-mono transition-colors">
              <UploadCloud className="w-3.5 h-3.5 text-cyan-400" />
              <span>{refFile ? refFile.name : 'Select Reference DEM (.tif)'}</span>
            </span>
          </label>

          {refFile && (
            <button
              onClick={handleUploadAndEvaluate}
              disabled={isEvaluating}
              className="px-4 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black font-semibold text-xs font-mono transition-colors shadow-sm shadow-cyan-500/20 flex items-center space-x-1.5"
            >
              {isEvaluating ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Evaluating...</span>
                </>
              ) : (
                <span>Compute Validation</span>
              )}
            </button>
          )}
        </div>
      </div>

      {evalError && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{evalError}</span>
        </div>
      )}

      {/* Metric Profile Selector Bar */}
      <div className="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5">
          <div className="flex items-center space-x-2">
            <SlidersHorizontal className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-mono font-bold text-white uppercase tracking-wider">
              Validation Metric Profile
            </h3>
            {isReconfiguring && (
              <span className="flex items-center text-cyan-400 text-[10px] font-mono gap-1">
                <RefreshCw className="w-3 h-3 animate-spin" />
                <span>Updating...</span>
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={() => setShowConfigDrawer(!showConfigDrawer)}
            className="flex items-center space-x-1.5 text-xs font-mono text-cyan-400 hover:text-cyan-300 transition-colors"
          >
            <Settings2 className="w-3.5 h-3.5" />
            <span>{showConfigDrawer ? 'Hide Metric Selection' : 'Customize Metrics (17 available)'}</span>
          </button>
        </div>

        {/* Preset Profile Pills */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 text-xs font-mono">
          {PRESET_PROFILES.map((prof) => {
            const isSelected = activeProfile === prof.id;
            return (
              <button
                key={prof.id}
                type="button"
                onClick={() => handleSelectProfile(prof.id)}
                className={`p-2.5 rounded-xl border text-left transition-all ${
                  isSelected
                    ? 'bg-cyan-500/15 border-cyan-500 text-cyan-200 shadow-sm shadow-cyan-500/20 ring-1 ring-cyan-500/30'
                    : 'bg-slate-950/60 border-slate-800/80 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                }`}
              >
                <div className="font-bold truncate text-[11px]">{prof.name}</div>
                <div className="text-[9px] text-slate-400 truncate mt-0.5">{prof.desc}</div>
              </button>
            );
          })}
        </div>

        {/* Custom Metric Checkbox Drawer */}
        {showConfigDrawer && (
          <div className="mt-3 pt-3 border-t border-slate-800 space-y-3">
            <div className="text-[10px] font-mono uppercase text-slate-400 tracking-wider">
              Configure Active Metrics ({selectedMetrics.length} selected):
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {ALL_METRICS.map((m) => {
                const isChecked = selectedMetrics.includes(m.key);
                return (
                  <label
                    key={m.key}
                    className={`flex items-start space-x-2.5 p-2 rounded-lg border cursor-pointer transition-colors text-xs font-mono ${
                      isChecked
                        ? 'bg-cyan-950/30 border-cyan-500/40 text-cyan-200'
                        : 'bg-slate-950/40 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => handleToggleMetric(m.key)}
                      className="mt-0.5 rounded border-slate-700 text-cyan-500 focus:ring-0 focus:ring-offset-0 bg-slate-900"
                    />
                    <div className="space-y-0.5 truncate">
                      <div className="font-bold text-[11px] truncate text-white">{m.name}</div>
                      <div className="text-[9px] text-slate-400 truncate">{m.description}</div>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* When evaluation is available */}
      {hasEval && evaluation && evaluation.metrics ? (
        <div className="space-y-8">
          {/* Dynamic Configured Metric Cards Grid */}
          <div>
            <div className="flex items-center justify-between mb-3 text-xs font-mono">
              <span className="text-slate-400 uppercase font-bold tracking-wider">
                Configured Metrics Results ({displayMetrics.length} Metrics Displayed)
              </span>
              {evaluation.reference_filename && (
                <span className="text-[11px] text-slate-400">
                  Reference: <span className="text-cyan-300 font-semibold">{evaluation.reference_filename}</span>
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {displayMetrics.map((m) => {
                const val = m.getValue(evaluation.metrics!);
                if (val === null || val === undefined) return null;

                const directionBg =
                  m.direction === 'lower'
                    ? 'bg-cyan-500/10 text-cyan-300 border-cyan-500/20'
                    : m.direction === 'zero'
                    ? 'bg-indigo-500/10 text-indigo-300 border-indigo-500/20'
                    : 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20';

                return (
                  <div
                    key={m.key}
                    className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-2 font-mono shadow-xl relative overflow-hidden group hover:border-slate-700 transition-colors"
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-[10px] text-slate-400 uppercase font-bold truncate">
                        {m.name}
                      </span>
                      <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold border uppercase tracking-wider shrink-0 ${directionBg}`}>
                        {m.directionLabel}
                      </span>
                    </div>

                    <div className="text-2xl font-bold text-white flex items-baseline gap-1">
                      <span>{m.format(val)}</span>
                    </div>

                    <p className="text-[10px] text-slate-400 font-sans leading-relaxed pt-1">
                      {m.description}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Secondary Statistical Overview Bar */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 rounded-xl bg-slate-900/60 border border-slate-800 font-mono text-xs">
            <div>
              <span className="text-slate-400 text-[10px] uppercase">Valid Evaluated Pixels</span>
              <div className="text-cyan-300 font-bold text-sm mt-0.5">
                {evaluation.metrics!.valid_pixel_count.toLocaleString()} px ({evaluation.metrics!.valid_pixel_pct !== undefined && evaluation.metrics!.valid_pixel_pct !== null ? `${evaluation.metrics!.valid_pixel_pct}%` : 'Unavailable'})
              </div>
            </div>
            <div>
              <span className="text-slate-400 text-[10px] uppercase">Ground Truth Span</span>
              <div className="text-white font-bold text-sm mt-0.5">
                {evaluation.metrics!.reference_min.toFixed(0)}m – {evaluation.metrics!.reference_max.toFixed(0)}m
              </div>
            </div>
            <div>
              <span className="text-slate-400 text-[10px] uppercase">Reconstructed Span</span>
              <div className="text-emerald-300 font-bold text-sm mt-0.5">
                {evaluation.metrics!.predicted_min.toFixed(0)}m – {evaluation.metrics!.predicted_max.toFixed(0)}m
              </div>
            </div>
            <div>
              <span className="text-slate-400 text-[10px] uppercase">Full Error Range</span>
              <div className="text-amber-300 font-bold text-sm mt-0.5">
                {evaluation.metrics!.min_error.toFixed(1)}m to {evaluation.metrics!.max_error.toFixed(1)}m
              </div>
            </div>
          </div>

          {/* Spatial Error Visualizer & Histogram Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left: Layer-switchable Error Map */}
            <div className="lg:col-span-7 space-y-3">
              <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3 shadow-xl">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-2">
                  <h3 className="text-sm font-bold text-white font-mono">
                    Evaluation Surface Inspection
                  </h3>
                  {/* Layer Tabs */}
                  <div className="flex items-center space-x-1 bg-slate-950/80 p-1 rounded-lg border border-slate-800 text-[11px] font-mono overflow-x-auto">
                    <button
                      onClick={() => setActiveLayer('signed_error')}
                      className={`px-2 py-1 rounded transition-colors whitespace-nowrap ${
                        activeLayer === 'signed_error'
                          ? 'bg-cyan-500 text-black font-bold'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Signed Error
                    </button>
                    <button
                      onClick={() => setActiveLayer('abs_error')}
                      className={`px-2 py-1 rounded transition-colors whitespace-nowrap ${
                        activeLayer === 'abs_error'
                          ? 'bg-cyan-500 text-black font-bold'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Absolute Error
                    </button>
                    <button
                      onClick={() => setActiveLayer('predicted')}
                      className={`px-2 py-1 rounded transition-colors whitespace-nowrap ${
                        activeLayer === 'predicted'
                          ? 'bg-cyan-500 text-black font-bold'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Predicted Height
                    </button>
                    <button
                      onClick={() => setActiveLayer('reference')}
                      className={`px-2 py-1 rounded transition-colors whitespace-nowrap ${
                        activeLayer === 'reference'
                          ? 'bg-cyan-500 text-black font-bold'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Reference Height
                    </button>
                    <button
                      onClick={() => setActiveLayer('hillshade')}
                      className={`px-2 py-1 rounded transition-colors whitespace-nowrap ${
                        activeLayer === 'hillshade'
                          ? 'bg-cyan-500 text-black font-bold'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Hillshade
                    </button>
                  </div>
                </div>

                <div
                  onClick={handleMapClick}
                  className="relative rounded-xl bg-slate-950 border border-slate-800 overflow-hidden aspect-square max-h-[460px] flex items-center justify-center cursor-crosshair group"
                  title="Click any pixel to inspect predicted elevation, reference height, and error"
                >
                  <img
                    src={getActiveLayerImage()}
                    alt="Evaluation Map Layer"
                    className="w-full h-full object-contain"
                  />

                  {/* Interactive Pixel Marker */}
                  {clickMarker && (
                    <div
                      className="absolute pointer-events-none transform -translate-x-1/2 -translate-y-1/2 z-20"
                      style={{ left: `${clickMarker.xPct * 100}%`, top: `${clickMarker.yPct * 100}%` }}
                    >
                      <div className="w-6 h-6 rounded-full border border-cyan-400 bg-cyan-400/20 animate-ping absolute -inset-1" />
                      <div className="w-4 h-4 rounded-full border-2 border-white bg-cyan-500 shadow-lg relative flex items-center justify-center">
                        <div className="w-1 h-1 bg-black rounded-full" />
                      </div>
                    </div>
                  )}

                  {/* Dynamic Legend */}
                  {activeLayer === 'signed_error' && (
                    <div className="absolute bottom-3 left-3 right-3 p-2 rounded-lg bg-black/85 backdrop-blur-md border border-slate-800 text-[10px] font-mono flex items-center justify-between text-slate-300 pointer-events-none">
                      <span className="text-blue-400">← Under-estimate (-ΔZ)</span>
                      <span className="text-slate-100">Zero Error (0m)</span>
                      <span className="text-rose-400">Over-estimate (+ΔZ) →</span>
                    </div>
                  )}
                  {activeLayer === 'abs_error' && (
                    <div className="absolute bottom-3 left-3 right-3 p-2 rounded-lg bg-black/85 backdrop-blur-md border border-slate-800 text-[10px] font-mono flex items-center justify-between text-slate-300 pointer-events-none">
                      <span className="text-emerald-400">Low Error (0m)</span>
                      <span className="text-amber-400">Moderate Error</span>
                      <span className="text-rose-500 font-bold">Max Error ({evaluation.metrics!.max_abs_error.toFixed(1)}m)</span>
                    </div>
                  )}
                  {activeLayer === 'predicted' && (
                    <div className="absolute bottom-3 left-3 right-3 p-2 rounded-lg bg-black/85 backdrop-blur-md border border-slate-800 text-[10px] font-mono flex items-center justify-between text-slate-300 pointer-events-none">
                      <span className="text-emerald-400">Min ({evaluation.metrics!.predicted_min.toFixed(0)}m)</span>
                      <span className="text-slate-100">Predicted DSM Height Map</span>
                      <span className="text-amber-400">Max ({evaluation.metrics!.predicted_max.toFixed(0)}m)</span>
                    </div>
                  )}
                  {activeLayer === 'reference' && (
                    <div className="absolute bottom-3 left-3 right-3 p-2 rounded-lg bg-black/85 backdrop-blur-md border border-slate-800 text-[10px] font-mono flex items-center justify-between text-slate-300 pointer-events-none">
                      <span className="text-emerald-400">Min ({evaluation.metrics!.reference_min.toFixed(0)}m)</span>
                      <span className="text-slate-100">Ground Truth Reference Height Map</span>
                      <span className="text-amber-400">Max ({evaluation.metrics!.reference_max.toFixed(0)}m)</span>
                    </div>
                  )}
                </div>

                {/* Interactive Pixel Inspection Card */}
                {inspectedPoint ? (
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-cyan-500/40 font-mono text-xs space-y-2.5 animate-fadeIn shadow-lg">
                    <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                      <div className="flex items-center space-x-2 text-cyan-300 font-bold text-[11px]">
                        <Crosshair className="w-3.5 h-3.5 text-cyan-400" />
                        <span>PIXEL INSPECTION [X: {inspectedPoint.pixel_coords.x}, Y: {inspectedPoint.pixel_coords.y}]</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => { setInspectedPoint(null); setClickMarker(null); }}
                        className="text-[10px] text-slate-400 hover:text-white transition-colors"
                      >
                        Dismiss
                      </button>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div className="p-2 rounded-lg bg-slate-900 border border-slate-800">
                        <span className="text-[9px] text-slate-400 uppercase block font-semibold">Predicted</span>
                        <span className="text-sm font-bold text-white mt-0.5 block">{inspectedPoint.predicted_height.toFixed(2)}m</span>
                      </div>
                      <div className="p-2 rounded-lg bg-slate-900 border border-slate-800">
                        <span className="text-[9px] text-slate-400 uppercase block font-semibold">Reference</span>
                        <span className="text-sm font-bold text-emerald-400 mt-0.5 block">
                          {inspectedPoint.reference_height !== null && inspectedPoint.reference_height !== undefined
                            ? `${inspectedPoint.reference_height.toFixed(2)}m`
                            : 'Unavailable'}
                        </span>
                      </div>
                      <div className="p-2 rounded-lg bg-slate-900 border border-slate-800">
                        <span className="text-[9px] text-slate-400 uppercase block font-semibold">Error (Residual)</span>
                        <span className={`text-sm font-bold mt-0.5 block ${
                          inspectedPoint.error === null || inspectedPoint.error === undefined
                            ? 'text-slate-400'
                            : inspectedPoint.error === 0
                            ? 'text-slate-200'
                            : inspectedPoint.error > 0
                            ? 'text-rose-400'
                            : 'text-blue-400'
                        }`}>
                          {inspectedPoint.error !== null && inspectedPoint.error !== undefined
                            ? `${inspectedPoint.error > 0 ? '+' : ''}${inspectedPoint.error.toFixed(2)}m`
                            : 'Unavailable'}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-900">
                      <span>Surface Slope: <strong className="text-slate-200">{inspectedPoint.slope_deg.toFixed(1)}°</strong></span>
                      {inspectedPoint.geo_coords && (
                        <span>
                          {inspectedPoint.geo_coords.lat !== undefined
                            ? `Lat ${inspectedPoint.geo_coords.lat.toFixed(5)}°, Lon ${inspectedPoint.geo_coords.lon?.toFixed(5)}°`
                            : `E ${inspectedPoint.geo_coords.x}, N ${inspectedPoint.geo_coords.y}`}
                        </span>
                      )}
                    </div>
                  </div>
                ) : isInspecting ? (
                  <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 font-mono text-[11px] text-cyan-400 flex items-center justify-center space-x-2">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Querying raster elevation at coordinate...</span>
                  </div>
                ) : (
                  <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800 text-[10px] font-mono text-slate-400 flex items-center space-x-2">
                    <MousePointerClick className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0" />
                    <span>Click any pixel on the surface map to inspect predicted height, ground truth reference, and vertical error.</span>
                  </div>
                )}
              </div>
            </div>

            {/* Right: Error Histogram & Scatter with 1:1 Reference Line */}
            <div className="lg:col-span-5 space-y-6">
              {/* Histogram */}
              <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3 shadow-xl">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <h3 className="text-xs font-bold text-white font-mono uppercase">
                    Error Distribution Frequency
                  </h3>
                  <span className="text-[10px] font-mono text-cyan-400">20 Bins</span>
                </div>

                <div className="h-52 w-full">
                  {evaluation.error_histogram && (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={evaluation.error_histogram} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                        <XAxis
                          dataKey="bin_start"
                          stroke="#64748b"
                          tick={{ fill: '#94a3b8', fontSize: 9, fontFamily: 'JetBrains Mono' }}
                          tickFormatter={(val) => `${val}m`}
                        />
                        <YAxis
                          stroke="#64748b"
                          tick={{ fill: '#94a3b8', fontSize: 9, fontFamily: 'JetBrains Mono' }}
                        />
                        <Tooltip
                          content={({ active, payload }) => {
                            if (active && payload && payload.length) {
                              const item = payload[0].payload;
                              return (
                                <div className="bg-slate-900 border border-slate-700 p-2 rounded font-mono text-[10px] text-white">
                                  <div>Error: {item.bin_label}</div>
                                  <div>Samples: {item.count} ({item.percentage}%)</div>
                                </div>
                              );
                            }
                            return null;
                          }}
                        />
                        <Bar dataKey="count" fill="#00f0ff" radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>

              {/* Scatter Plot: Predicted vs Reference with 1:1 Line */}
              <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3 shadow-xl">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <h3 className="text-xs font-bold text-white font-mono uppercase">
                    Elevation Scatter vs 1:1 Ideal Line
                  </h3>
                  <span className="text-[10px] font-mono text-emerald-400">
                    r = {evaluation.metrics!.pearson_r.toFixed(3)}
                  </span>
                </div>

                <div className="h-52 w-full">
                  {evaluation.scatter_samples && (
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart margin={{ top: 5, right: 15, left: -20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                        <XAxis
                          dataKey="reference"
                          name="Reference (m)"
                          stroke="#64748b"
                          domain={[scatterMin, scatterMax]}
                          tick={{ fill: '#94a3b8', fontSize: 9, fontFamily: 'JetBrains Mono' }}
                        />
                        <YAxis
                          dataKey="predicted"
                          name="Predicted (m)"
                          stroke="#64748b"
                          domain={[scatterMin, scatterMax]}
                          tick={{ fill: '#94a3b8', fontSize: 9, fontFamily: 'JetBrains Mono' }}
                        />
                        <ReferenceLine
                          segment={[{ x: scatterMin, y: scatterMin }, { x: scatterMax, y: scatterMax }]}
                          stroke="#00f0ff"
                          strokeDasharray="4 4"
                          strokeWidth={1.5}
                          label={{ value: "1:1 Ideal", fill: "#00f0ff", fontSize: 9, position: "top" }}
                        />
                        <Tooltip
                          content={({ active, payload }) => {
                            if (active && payload && payload.length) {
                              const p = payload[0].payload;
                              return (
                                <div className="bg-slate-900 border border-slate-700 p-2 rounded font-mono text-[10px] text-white">
                                  <div>Ref: {p.reference}m</div>
                                  <div>Pred: {p.predicted}m</div>
                                  <div>Residual: {p.error}m</div>
                                </div>
                              );
                            }
                            return null;
                          }}
                        />
                        <Scatter data={evaluation.scatter_samples} fill="#10b981" fillOpacity={0.75} />
                      </ScatterChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Topographic Landscape & Scene Stratification Evaluation Breakdown Table */}
          {evaluation.landscape_evaluation && evaluation.landscape_evaluation.length > 0 && (
            <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4 font-mono shadow-xl">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center space-x-2">
                  <FileCheck className="w-4 h-4 text-emerald-400" />
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                    Scene Stratification & Topographical Accuracy Breakdown
                  </h3>
                </div>
                <span className="text-[10px] text-slate-400">Independent Strata Evaluation • Un-fabricated</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-950/60 text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="p-3">STRATA CATEGORY</th>
                      <th className="p-3">VALID SAMPLES</th>
                      <th className="p-3">MAE (m)</th>
                      <th className="p-3">RMSE (m)</th>
                      <th className="p-3">CORRELATION (r)</th>
                      <th className="p-3">BIAS (m)</th>
                      <th className="p-3">MEDIAN AE (m)</th>
                      <th className="p-3">FIDELITY RATING</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {evaluation.landscape_evaluation.map((row, idx) => (
                      <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                        <td className="p-3 font-bold text-white flex items-center space-x-2">
                          <span className={`w-2 h-2 rounded-full ${idx === 0 ? 'bg-emerald-400' : idx === 1 ? 'bg-amber-400' : idx === 2 ? 'bg-cyan-400' : 'bg-rose-400'}`} />
                          <span>{row.landscape_type}</span>
                        </td>
                        <td className="p-3 text-slate-300">{row.sample_count.toLocaleString()}</td>
                        <td className="p-3 font-bold text-cyan-300">{row.mae.toFixed(2)}m</td>
                        <td className="p-3 font-bold text-white">{row.rmse.toFixed(2)}m</td>
                        <td className="p-3 font-bold text-emerald-400">{row.pearson_r.toFixed(3)}</td>
                        <td className="p-3 font-medium text-slate-300">
                          {row.bias !== null && row.bias !== undefined
                            ? (row.bias > 0 ? `+${row.bias.toFixed(2)}m` : `${row.bias.toFixed(2)}m`)
                            : '—'}
                        </td>
                        <td className="p-3 font-medium text-slate-300">
                          {row.median_abs_error !== null && row.median_abs_error !== undefined
                            ? `${row.median_abs_error.toFixed(2)}m`
                            : '—'}
                        </td>
                        <td className="p-3">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              row.pearson_r > 0.8
                                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                : row.pearson_r > 0.5
                                ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                                : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                            }`}
                          >
                            {row.pearson_r > 0.8 ? 'EXCELLENT' : row.pearson_r > 0.5 ? 'MODERATE' : 'COARSE'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      ) : (
        /* Empty / Honest State when no ground truth is available */
        <div className="p-12 rounded-3xl bg-slate-900/40 border border-slate-800 text-center max-w-2xl mx-auto space-y-4">
          <div className="w-14 h-14 rounded-2xl bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center justify-center mx-auto">
            <AlertCircle className="w-7 h-7" />
          </div>

          <h3 className="text-lg font-bold text-white font-mono uppercase">
            Validation Unavailable
          </h3>

          <p className="text-xs text-slate-400 leading-relaxed max-w-md mx-auto">
            In compliance with ISRO remote-sensing standards, elevation metrics (MAE, RMSE, Pearson r)
            are never fabricated or simulated. Upload a true reference DEM or LiDAR GeoTIFF above to evaluate accuracy.
          </p>

          <div className="pt-2">
            <label className="inline-block cursor-pointer">
              <input
                type="file"
                accept=".tif,.tiff,.npy"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && setRefFile(e.target.files[0])}
              />
              <span className="px-5 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-semibold text-xs font-mono transition-colors shadow-lg shadow-cyan-500/20">
                Upload Ground Truth DEM GeoTIFF
              </span>
            </label>
          </div>
        </div>
      )}
    </div>
  );
};
