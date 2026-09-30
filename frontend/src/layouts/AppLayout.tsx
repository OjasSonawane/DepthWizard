import React from 'react';
import { useProject, NavTab } from '../context/ProjectContext';
import {
  Layers,
  Box,
  BarChart2,
  CheckCircle2,
  FileText,
  UploadCloud,
  Download,
  Cpu,
  Globe2,
  Activity,
  Compass,
  Home,
  RefreshCw,
  AlertCircle
} from 'lucide-react';

interface AppLayoutProps {
  children: React.ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  const {
    activeTab,
    setActiveTab,
    currentJobId,
    results,
    jobStatus,
    deviceInfo,
    resetProject,
    setIsExportOpen,
    activeDataset
  } = useProject();

  const isDemo = activeDataset?.source === 'preloaded' || currentJobId?.startsWith('dw_demo_');

  // Compute status
  let statusText = 'READY';
  let statusColor = 'text-slate-400 border-slate-700 bg-slate-800/60';
  let dotColor = 'bg-slate-400';

  const st = jobStatus?.status?.toUpperCase();

  if (st === 'FAILED' || st === 'ERROR') {
    statusText = 'ERROR';
    statusColor = 'text-rose-400 border-rose-500/30 bg-rose-500/10';
    dotColor = 'bg-rose-400';
  } else if (st === 'CALIBRATING') {
    statusText = 'CALIBRATING';
    statusColor = 'text-indigo-400 border-indigo-500/30 bg-indigo-500/10';
    dotColor = 'bg-indigo-400 animate-pulse';
  } else if (st === 'QUEUED') {
    statusText = 'QUEUED';
    statusColor = 'text-amber-400 border-amber-500/30 bg-amber-500/10';
    dotColor = 'bg-amber-400 animate-pulse';
  } else if (['VALIDATING', 'INFERENCE', 'GENERATING_DSM', 'VALIDATING_RESULT', 'PROCESSING'].includes(st || '')) {
    statusText = st === 'PROCESSING' ? 'PROCESSING' : (st || 'PROCESSING');
    statusColor = 'text-cyan-400 border-cyan-500/30 bg-cyan-500/10';
    dotColor = 'bg-cyan-400 animate-ping';
  } else if (st === 'COMPLETED' || results) {
    statusText = 'COMPLETE';
    statusColor = 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10';
    dotColor = 'bg-emerald-400';
  }

  const navItems: { id: NavTab; label: string; icon: React.ReactNode; requiresResults?: boolean }[] = [
    { id: 'landing', label: 'Overview', icon: <Home className="w-4 h-4" /> },
    { id: 'upload', label: 'Reconstruction', icon: <UploadCloud className="w-4 h-4" /> },
    { id: 'depth', label: 'Depth Map', icon: <Layers className="w-4 h-4" />, requiresResults: true },
    { id: 'dsm', label: 'Surface Model (DSM)', icon: <Globe2 className="w-4 h-4" />, requiresResults: true },
    { id: 'explorer', label: '3D Explorer', icon: <Box className="w-4 h-4 text-cyan-400" />, requiresResults: true },
    { id: 'analysis', label: 'Disaster Analytics', icon: <BarChart2 className="w-4 h-4" />, requiresResults: true },
    { id: 'validation', label: 'Model Validation', icon: <CheckCircle2 className="w-4 h-4" />, requiresResults: true },
    { id: 'methodology', label: 'Methodology', icon: <FileText className="w-4 h-4" /> },
  ];

  return (
    <div className="flex h-screen w-screen bg-[#070b12] text-slate-200 overflow-hidden font-sans select-none">
      {/* Left Sidebar */}
      <aside className="w-64 flex-shrink-0 bg-[#0a0f1c]/90 border-r border-slate-800/80 backdrop-blur-md flex flex-col z-20">
        {/* Brand Header */}
        <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
          <div 
            onClick={() => setActiveTab('landing')}
            className="flex items-center space-x-3 cursor-pointer group"
          >
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20 group-hover:scale-105 transition-transform">
              <Compass className="w-5 h-5 text-black" />
            </div>
            <div>
              <div className="text-base font-bold tracking-wider text-white flex items-center gap-1.5">
                DEPTH<span className="text-cyan-400">WIZARD</span>
              </div>
              <div className="text-[10px] font-mono text-cyan-500/80 uppercase tracking-widest">
                ISRO EO-GEOINT
              </div>
            </div>
          </div>
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          <div className="px-3 pb-2 text-[10px] font-mono uppercase tracking-wider text-slate-400 font-bold">
            Navigation
          </div>
          {navItems.map((item) => {
            const isDisabled = item.requiresResults && !results;
            const isActive = activeTab === item.id;

            return (
              <button
                key={item.id}
                disabled={isDisabled}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 shadow-sm shadow-cyan-500/10'
                    : isDisabled
                    ? 'text-slate-400 hover:text-slate-300 opacity-60 cursor-not-allowed'
                    : 'text-slate-300 hover:text-white hover:bg-slate-800/50'
                }`}
              >
                <div className="flex items-center space-x-3">
                  <span className={isActive ? 'text-cyan-400' : 'text-slate-300'}>
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </div>
                {item.requiresResults && results && (
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50" />
                )}
              </button>
            );
          })}
        </nav>

        {/* Active Dataset & Project Meta Card */}
        {activeDataset ? (
          <div className="p-3 mx-3 mb-3 rounded-lg bg-slate-900/90 border border-slate-800 text-[11px] space-y-2 shadow-md">
            <div className="flex items-center justify-between font-mono text-[10px]">
              <span className={`px-1.5 py-0.5 rounded font-bold ${
                activeDataset.source === 'user_upload'
                  ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/30'
                  : 'bg-indigo-500/15 text-indigo-300 border border-indigo-500/30'
              }`}>
                {activeDataset.source === 'user_upload' ? 'USER UPLOAD' : 'PRELOADED'}
              </span>
              <span className={`flex items-center gap-1 font-bold ${
                results || activeDataset.status === 'completed'
                  ? 'text-emerald-400'
                  : ['VALIDATING', 'INFERENCE', 'CALIBRATING', 'GENERATING_DSM', 'VALIDATING_RESULT', 'processing'].includes(jobStatus?.status || '')
                  ? 'text-cyan-400'
                  : 'text-slate-400'
              }`}>
                <span className={`w-1.5 h-1.5 rounded-full ${
                  results || activeDataset.status === 'completed'
                    ? 'bg-emerald-400'
                    : ['VALIDATING', 'INFERENCE', 'CALIBRATING', 'GENERATING_DSM', 'VALIDATING_RESULT', 'processing'].includes(jobStatus?.status || '')
                    ? 'bg-cyan-400 animate-ping'
                    : 'bg-slate-500'
                }`} />
                {results || activeDataset.status === 'completed' ? '3D READY' : ['VALIDATING', 'INFERENCE', 'CALIBRATING', 'GENERATING_DSM', 'VALIDATING_RESULT', 'processing'].includes(jobStatus?.status || '') ? (jobStatus?.status?.toUpperCase() || 'PROCESSING') : 'SELECTED'}
              </span>
            </div>

            <div className="flex items-center space-x-2.5 pt-0.5">
              <img
                src={activeDataset.thumbnail_url}
                alt={activeDataset.name}
                className="w-10 h-10 rounded object-cover border border-slate-700/80 bg-slate-950 flex-shrink-0"
                onError={(e) => {
                  (e.target as HTMLElement).style.display = 'none';
                }}
              />
              <div className="min-w-0 flex-1">
                <div className="truncate font-mono text-cyan-300 text-xs font-semibold" title={activeDataset.name}>
                  {activeDataset.name}
                </div>
                <div className="text-[10px] text-slate-400 font-mono uppercase">
                  {activeDataset.file_type} • {activeDataset.width}×{activeDataset.height}
                </div>
              </div>
            </div>

            <div className="space-y-1 pt-1 border-t border-slate-800/80 text-[10px] font-mono">
              <div className="flex items-center justify-between text-slate-400">
                <span>CRS:</span>
                <span className="text-slate-200 truncate max-w-[120px]" title={activeDataset.crs || 'Unavailable'}>
                  {activeDataset.crs || 'Unavailable'}
                </span>
              </div>
              {results && (
                <div className="flex items-center justify-between text-slate-400">
                  <span>Relief:</span>
                  <span className="text-emerald-400 font-semibold">
                    {results.dsm_stats.relief} {results.dsm_stats.is_metric ? 'm' : 'rel'}
                  </span>
                </div>
              )}
            </div>

            <div className="flex items-center gap-1.5 pt-1">
              {results ? (
                <button
                  onClick={resetProject}
                  className="flex-1 flex items-center justify-center space-x-1 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] transition-colors"
                  title="Clear active job and select another dataset"
                >
                  <RefreshCw className="w-3 h-3" />
                  <span>Reset Run</span>
                </button>
              ) : (
                <button
                  onClick={() => setActiveTab('upload')}
                  className="w-full flex items-center justify-center space-x-1 py-1.5 rounded bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-[10px] transition-colors"
                >
                  <span>Open in Workspace</span>
                </button>
              )}
            </div>
          </div>
        ) : results ? (
          <div className="p-3 mx-3 mb-3 rounded-lg bg-slate-900/90 border border-slate-800 text-[11px] space-y-2">
            <div className="flex items-center justify-between text-slate-400 font-mono text-[10px]">
              <span>{isDemo ? 'DEMO RECONSTRUCTION' : 'ACTIVE RECONSTRUCTION'}</span>
              <span className="text-emerald-400">ONLINE</span>
            </div>
            <div className="truncate font-mono text-cyan-300" title={results.filename}>
              {results.filename}
            </div>
            <div className="flex items-center justify-between text-slate-400 font-mono text-[10px]">
              <span>CRS:</span>
              <span className="text-slate-200">{results.image_metadata.crs || 'Unavailable'}</span>
            </div>
            <div className="flex items-center justify-between text-slate-400 font-mono text-[10px]">
              <span>Relief:</span>
              <span className="text-slate-200">
                {results.dsm_stats.relief} {results.dsm_stats.is_metric ? 'm' : 'rel'}
              </span>
            </div>
            <button
              onClick={resetProject}
              className="w-full mt-2 flex items-center justify-center space-x-1.5 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] transition-colors"
            >
              <RefreshCw className="w-3 h-3" />
              <span>New Reconstruction</span>
            </button>
          </div>
        ) : null}

        {/* Bottom Hardware Info */}
        <div className="p-3 border-t border-slate-800/80 bg-slate-950/40 flex items-center justify-between text-[11px] font-mono">
          <div className="flex items-center space-x-2">
            <Cpu className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-slate-400">ACCEL:</span>
            <span className="text-cyan-300 font-bold">
              {deviceInfo?.device || 'MPS/CPU'}
            </span>
          </div>
          <div className="flex items-center space-x-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[10px] text-slate-400">v1.0</span>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        {/* Top Telemetry Header */}
        <header className="h-14 bg-[#0a0f1c]/70 border-b border-slate-800/80 backdrop-blur-md px-6 flex items-center justify-between z-10">
          <div className="flex items-center space-x-4">
            <div className="text-xs font-mono tracking-wider text-slate-400 flex items-center gap-2">
              <Activity className="w-3.5 h-3.5 text-cyan-400" />
              <span>SUBSYSTEM:</span>
              <span className="text-cyan-300 font-semibold uppercase">
                {activeTab.replace('_', ' ')}
              </span>
            </div>

            {/* Status Pill */}
            <div className={`px-2.5 py-0.5 rounded-full border text-[10px] font-mono flex items-center space-x-1.5 ${statusColor}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
              <span className="font-bold">{statusText}</span>
            </div>

            {currentJobId && (
              <div className="px-2 py-0.5 rounded bg-slate-800/80 border border-slate-700/60 font-mono text-[10px] text-slate-300">
                {isDemo ? `DEMO: ${currentJobId}` : `JOB: ${currentJobId}`}
              </div>
            )}

            {activeDataset && (
              <div className="hidden lg:flex items-center space-x-2 text-[11px] font-mono">
                <span className={`px-2 py-0.5 rounded text-[10px] border ${
                  activeDataset.source === 'user_upload'
                    ? 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30'
                    : 'bg-indigo-500/10 text-indigo-300 border-indigo-500/30'
                }`}>
                  {activeDataset.source === 'user_upload' ? 'USER UPLOAD' : 'PRELOADED'}
                </span>
                <span className="text-white font-semibold truncate max-w-[180px]" title={activeDataset.name}>
                  {activeDataset.name}
                </span>
                <span className="text-slate-600">|</span>
                <span className="text-slate-400">
                  {activeDataset.width}×{activeDataset.height} px
                </span>
                <span className="text-slate-600">|</span>
                <span className={activeDataset.georeferenced ? 'text-emerald-400' : 'text-slate-400'}>
                  {activeDataset.georeferenced ? (activeDataset.crs || 'Unavailable') : 'Unavailable'}
                </span>
              </div>
            )}

            {results && !activeDataset && (
              <div className="hidden md:flex items-center space-x-2 text-[11px]">
                <span className="px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-mono">
                  {results.is_georeferenced ? 'GEOREFERENCED (DSM)' : 'RELATIVE (rDSM)'}
                </span>
                <span className="text-slate-600">|</span>
                <span className="text-slate-400 font-mono text-[11px]">
                  {results.image_metadata.width}x{results.image_metadata.height} px
                </span>
              </div>
            )}
          </div>

          <div className="flex items-center space-x-3">
            {results && (
              <button
                onClick={() => setIsExportOpen(true)}
                className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 text-cyan-300 border border-cyan-500/30 text-xs font-medium transition-all shadow-sm shadow-cyan-500/10"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Export Project</span>
              </button>
            )}
            <button
              onClick={() => setActiveTab('methodology')}
              className="text-xs text-slate-400 hover:text-slate-200 transition-colors font-medium"
            >
              Docs & Methodology
            </button>
          </div>
        </header>

        {/* Viewport Content */}
        <main className="flex-1 relative overflow-y-auto bg-[#070b12]">
          {children}
        </main>
      </div>
    </div>
  );
};
