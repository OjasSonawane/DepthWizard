import React from 'react';
import { useProject } from '../context/ProjectContext';
import { api } from '../services/api';
import {
  ArrowRight,
  Layers,
  Globe,
  Box,
  ShieldAlert,
  Cpu,
  Sparkles,
  ChevronRight,
  Database
} from 'lucide-react';

export const LandingPage: React.FC = () => {
  const { setActiveTab, setCurrentJobId } = useProject();

  const handleLaunchSample = async (sampleId: string) => {
    try {
      const resp = await api.loadSample(sampleId);
      setCurrentJobId(resp.job_id);
      setActiveTab('upload');
    } catch (e) {
      console.error('Failed to load sample:', e);
      setActiveTab('upload');
    }
  };

  return (
    <div className="min-h-full pb-16">
      {/* Hero Section */}
      <section className="relative overflow-hidden pt-12 pb-20 px-6 sm:px-12 border-b border-slate-800/80 bg-gradient-to-b from-[#0e1628]/60 via-[#070b12] to-[#070b12]">
        {/* Glow ambient backgrounds */}
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute top-1/3 right-1/4 w-96 h-96 bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />

        <div className="max-w-6xl mx-auto relative z-10">
          {/* Badge */}
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/25 text-cyan-300 text-xs font-mono mb-6">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
            <span>ISRO DISASTER MANAGEMENT THEME • AI EO-GEOINT</span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
            <div className="lg:col-span-7 space-y-6">
              <h1 className="text-4xl sm:text-6xl font-extrabold text-white tracking-tight leading-none">
                From One Image to an{' '}
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-sky-300 to-blue-500">
                  Explorable 3D World
                </span>
              </h1>

              <p className="text-base sm:text-lg text-slate-300 leading-relaxed max-w-xl">
                AI-powered single-view elevation reconstruction for remote sensing,
                terrain intelligence, and disaster management. Transform RGB satellite & aerial
                imagery into georeferenced Digital Surface Models (DSM) and interactive 3D flythroughs.
              </p>

              {/* CTAs */}
              <div className="flex flex-wrap items-center gap-4 pt-2">
                <button
                  onClick={() => setActiveTab('upload')}
                  className="flex items-center space-x-2.5 px-6 py-3 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 text-black font-semibold text-sm hover:from-cyan-400 hover:to-blue-500 transition-all shadow-lg shadow-cyan-500/20 hover:scale-[1.02]"
                >
                  <span>Launch Workspace</span>
                  <ArrowRight className="w-4 h-4" />
                </button>

                <button
                  onClick={() => setActiveTab('methodology')}
                  className="flex items-center space-x-2 px-5 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700 text-sm font-medium transition-colors"
                >
                  <span>Explore Methodology</span>
                </button>

                <button
                  onClick={() => handleLaunchSample('himalayan_valley')}
                  className="flex items-center space-x-2 px-4 py-3 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-xs font-mono transition-colors"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Try Demo Dataset</span>
                </button>
              </div>

              {/* Pipeline summary ticker */}
              <div className="pt-6 grid grid-cols-3 gap-4 border-t border-slate-800/80 text-xs font-mono">
                <div>
                  <div className="text-slate-400">INPUT IMAGERY</div>
                  <div className="text-white font-bold text-sm mt-0.5">GeoTIFF / JPG</div>
                </div>
                <div>
                  <div className="text-slate-400">SURFACE MODEL</div>
                  <div className="text-cyan-400 font-bold text-sm mt-0.5">DSM / rDSM</div>
                </div>
                <div>
                  <div className="text-slate-400">SCIENTIFIC ACCURACY</div>
                  <div className="text-emerald-400 font-bold text-sm mt-0.5">DSM Validation</div>
                </div>
              </div>
            </div>

            {/* Hero Visual Card (Explicitly labeled as DEMO) */}
            <div className="lg:col-span-5">
              <div className="rounded-2xl p-1 bg-gradient-to-b from-cyan-500/30 via-slate-800 to-slate-900/60 shadow-2xl shadow-cyan-500/10">
                <div className="bg-[#0b101c] rounded-[15px] p-6 space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                    <div className="flex items-center space-x-2 font-mono text-xs text-cyan-300">
                      <Box className="w-4 h-4 text-cyan-400" />
                      <span>DEMO RECONSTRUCTION</span>
                    </div>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-bold">
                      DEMO DATASET
                    </span>
                  </div>

                  <div className="relative aspect-video rounded-xl bg-slate-950 border border-slate-800 overflow-hidden flex items-center justify-center group">
                    <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-slate-950 to-cyan-950/40 flex items-center justify-center">
                      <div className="text-center space-y-1 p-4">
                        <Box className="w-8 h-8 text-cyan-400 mx-auto animate-pulse" />
                        <div className="text-xs font-mono font-bold text-white">Himalayan Topography Scene</div>
                        <div className="text-[10px] font-mono text-slate-400">UTM 43N • EPSG:32643 • 10m GSD</div>
                      </div>
                    </div>
                    <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between text-[11px] font-mono">
                      <span className="text-slate-300">Bundled Demo Package</span>
                      <span className="text-cyan-400 font-bold">Reference DEM + GCPs</span>
                    </div>
                  </div>

                  {/* Feature specs */}
                  <div className="space-y-2 text-xs font-mono text-slate-300">
                    <div className="flex items-center justify-between py-1 border-b border-slate-800/60">
                      <span className="text-slate-400">Scale Calibration</span>
                      <span className="text-cyan-300">SRTM DEM / GCP Huber Regression</span>
                    </div>
                    <div className="flex items-center justify-between py-1 border-b border-slate-800/60">
                      <span className="text-slate-400">Mesh Triangulation</span>
                      <span className="text-slate-200">Multi-LOD (64 to 256 Vtx)</span>
                    </div>
                    <div className="flex items-center justify-between py-1">
                      <span className="text-slate-400">Disaster Modules</span>
                      <span className="text-emerald-400">Flood Inundation & Slope Risk</span>
                    </div>
                  </div>

                  <button
                    onClick={() => handleLaunchSample('himalayan_valley')}
                    className="w-full py-2.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 text-xs font-mono font-semibold transition-colors flex items-center justify-center space-x-2"
                  >
                    <span>Load Demo Reconstruction</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* How it Works Section */}
      <section className="py-16 px-6 sm:px-12 max-w-6xl mx-auto">
        <div className="text-center space-y-2 mb-12">
          <div className="text-xs font-mono text-cyan-400 uppercase tracking-widest">
            OPERATIONAL WORKFLOW
          </div>
          <h2 className="text-2xl sm:text-3xl font-bold text-white">
            End-to-End Elevation Reconstruction Pipeline
          </h2>
          <p className="text-sm text-slate-400 max-w-lg mx-auto">
            From single-view 2D optical satellite imagery to metric 3D digital surface models with scientific validation.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          {[
            {
              step: '01',
              title: 'Upload Imagery',
              desc: 'GeoTIFF or optical JPG/PNG with automatic CRS and affine transform preservation.',
              icon: <Globe className="w-5 h-5 text-cyan-400" />
            },
            {
              step: '02',
              title: 'AI Depth Inference',
              desc: 'Monocular transformer estimates relative depth geometry and structural breaks.',
              icon: <Layers className="w-5 h-5 text-blue-400" />
            },
            {
              step: '03',
              title: 'Scale Calibration',
              desc: 'Robust regression against reference DEM (SRTM/CartoDEM) or Ground Control Points.',
              icon: <Cpu className="w-5 h-5 text-indigo-400" />
            },
            {
              step: '04',
              title: 'DSM & Slope Generation',
              desc: 'Calculates Horn gradient slope, 315° hillshade, and georeferenced DSM GeoTIFF.',
              icon: <ShieldAlert className="w-5 h-5 text-amber-400" />
            },
            {
              step: '05',
              title: '3D World Flythrough',
              desc: 'Interactive Three.js scene with point height inspection, transect profiles, and flood simulation.',
              icon: <Box className="w-5 h-5 text-emerald-400" />
            }
          ].map((item, i) => (
            <div
              key={i}
              className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-cyan-500/40 transition-colors space-y-3"
            >
              <div className="flex items-center justify-between">
                <div className="p-2 rounded-lg bg-slate-800/80 border border-slate-700/60">
                  {item.icon}
                </div>
                <span className="text-xs font-mono text-slate-500 font-bold">{item.step}</span>
              </div>
              <h3 className="text-sm font-bold text-white">{item.title}</h3>
              <p className="text-xs text-slate-400 leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Disaster Management Theme Highlights */}
      <section className="py-12 px-6 sm:px-12 bg-slate-900/40 border-y border-slate-800/80">
        <div className="max-w-6xl mx-auto space-y-8">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div>
              <div className="text-xs font-mono text-cyan-400 uppercase tracking-wider">
                DISASTER RESILIENCE & RESPONSE
              </div>
              <h2 className="text-2xl font-bold text-white mt-1">
                Geospatial Decision Support Tools
              </h2>
            </div>
            <button
              onClick={() => handleLaunchSample('coastal_estuary')}
              className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-mono transition-colors self-start md:self-auto"
            >
              <Database className="w-3.5 h-3.5 text-cyan-400" />
              <span>Load Coastal Flood Demo</span>
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3">
              <div className="w-8 h-8 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20 flex items-center justify-center font-mono text-xs font-bold">
                FL
              </div>
              <h3 className="text-base font-bold text-white">Illustrative Flood Simulation</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Adjust water surface threshold dynamically in 3D to identify low-lying terrain zones and estimate inundated area percentages.
              </p>
            </div>

            <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3">
              <div className="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center justify-center font-mono text-xs font-bold">
                SL
              </div>
              <h3 className="text-base font-bold text-white">Slope Instability & Landslide Screening</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Horn 3x3 finite-difference gradient calculations identify steep gradients (&gt;30°) susceptible to debris flows, avalanches, and rockfalls.
              </p>
            </div>

            <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center justify-center font-mono text-xs font-bold">
                PR
              </div>
              <h3 className="text-base font-bold text-white">Interactive Cross-Section Profiles</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Draw a transect line across the terrain to extract continuous elevation cross-sections, cumulative gains, and relief variability.
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
