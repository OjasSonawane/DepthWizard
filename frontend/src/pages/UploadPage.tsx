import React, { useState, useEffect } from 'react';
import { useProject } from '../context/ProjectContext';
import { api } from '../services/api';
import { DatasetSummary, GCPItem, InputValidationResult } from '../types';
import {
  UploadCloud,
  Layers,
  Globe,
  CheckCircle2,
  AlertTriangle,
  Play,
  ArrowRight,
  RefreshCw,
  Plus,
  Trash2,
  Table,
  Database,
  Eye,
  FolderOpen,
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  XCircle,
  HelpCircle,
  Check,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

export const UploadPage: React.FC = () => {
  const {
    datasets,
    activeDatasetId,
    activeDataset,
    isLoadingDatasets,
    selectDataset,
    uploadDataset,
    deleteDataset,
    refreshDatasets,
    currentJobId,
    setCurrentJobId,
    results,
    setResults,
    setActiveTab,
    loadJobResults,
    jobStatus,
    setJobStatus
  } = useProject();

  // Filter state for Dataset Library
  const [filterTab, setFilterTab] = useState<'all' | 'user' | 'preloaded'>('all');

  // File upload state
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [demFile, setDemFile] = useState<File | null>(null);
  const [gcpFile, setGcpFile] = useState<File | null>(null);

  // Pre-upload validation state
  const [stagedValidation, setStagedValidation] = useState<InputValidationResult | null>(null);
  const [isValidatingStaged, setIsValidatingStaged] = useState<boolean>(false);
  const [showActiveStages, setShowActiveStages] = useState<boolean>(false);

  // UI state
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // GCPs state for active dataset
  const [gcps, setGcps] = useState<GCPItem[]>([]);
  const [newGcpId, setNewGcpId] = useState<string>('');
  const [newGcpX, setNewGcpX] = useState<string>('');
  const [newGcpY, setNewGcpY] = useState<string>('');
  const [newGcpElev, setNewGcpElev] = useState<string>('');

  // Validate staged image file immediately when selected
  useEffect(() => {
    if (!imageFile) {
      setStagedValidation(null);
      return;
    }
    let isMounted = true;
    setIsValidatingStaged(true);
    api.validateInput(imageFile)
      .then((res) => {
        if (isMounted) {
          setStagedValidation(res);
          setIsValidatingStaged(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          console.error('Pre-upload validation check failed:', err);
          setIsValidatingStaged(false);
        }
      });
    return () => {
      isMounted = false;
    };
  }, [imageFile]);

  // Sync GCPs when active dataset changes
  useEffect(() => {
    if (activeDataset?.parsed_gcps && activeDataset.parsed_gcps.length > 0) {
      setGcps(activeDataset.parsed_gcps);
    } else {
      setGcps([]);
    }
  }, [activeDataset?.id, activeDataset?.parsed_gcps]);

  // Poll job status if processing
  useEffect(() => {
    let interval: any;
    if (isProcessing && currentJobId) {
      interval = setInterval(async () => {
        try {
          const status = await api.getJobStatus(currentJobId);
          setJobStatus(status);
          const st = status.status ? status.status.toUpperCase() : '';
          if (st === 'COMPLETED') {
            setIsProcessing(false);
            clearInterval(interval);
            await loadJobResults(currentJobId);
            await refreshDatasets();
          } else if (st === 'FAILED') {
            setIsProcessing(false);
            setErrorMsg(status.errors || status.error || 'Reconstruction processing failed.');
            clearInterval(interval);
          }
        } catch (e) {
          console.error('Failed to poll job status:', e);
        }
      }, 800);
    }
    return () => clearInterval(interval);
  }, [isProcessing, currentJobId]);

  // Handle uploading user imagery & persisting to library
  const handleUploadDataset = async () => {
    if (!imageFile) return;
    setIsUploading(true);
    setErrorMsg(null);
    try {
      await uploadDataset(imageFile, demFile, gcpFile);
      setImageFile(null);
      setDemFile(null);
      setGcpFile(null);
      setIsUploading(false);
    } catch (err: any) {
      setErrorMsg(err.message || 'Dataset upload failed.');
      setIsUploading(false);
    }
  };

  // Handle selecting a dataset from the library
  const handleSelectDataset = async (datasetId: string) => {
    setErrorMsg(null);
    try {
      await selectDataset(datasetId);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to select dataset.');
    }
  };

  // Handle deleting a user-uploaded dataset
  const handleDeleteDataset = async (e: React.MouseEvent, dataset: DatasetSummary) => {
    e.stopPropagation();
    if (!window.confirm(`Delete dataset "${dataset.name}" and all associated files from disk?`)) {
      return;
    }
    try {
      await deleteDataset(dataset.id);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to delete dataset.');
    }
  };

  // Handle starting reconstruction on the active dataset
  const handleStartReconstruction = async () => {
    if (!activeDataset) return;
    setIsProcessing(true);
    setErrorMsg(null);
    try {
      const { job_id } = await api.prepareJob(activeDataset.id);
      setCurrentJobId(job_id);

      api.startProcessing(job_id)
        .then(async (summary) => {
          setResults(summary);
          setIsProcessing(false);
          await refreshDatasets();
        })
        .catch((err) => {
          setErrorMsg(err.message || 'Reconstruction processing failed.');
          setIsProcessing(false);
        });
    } catch (err: any) {
      setErrorMsg(err.message || 'Could not initiate reconstruction.');
      setIsProcessing(false);
    }
  };

  // GCP handlers
  const handleAddGcp = () => {
    if (!newGcpId || !newGcpX || !newGcpY || !newGcpElev) return;
    const item: GCPItem = {
      id: newGcpId,
      x: parseFloat(newGcpX),
      y: parseFloat(newGcpY),
      elevation: parseFloat(newGcpElev)
    };
    const updated = [...gcps, item];
    setGcps(updated);
    setNewGcpId('');
    setNewGcpX('');
    setNewGcpY('');
    setNewGcpElev('');

    if (currentJobId) {
      api.calibrateWithGCPs(currentJobId, updated).catch(console.error);
    }
  };

  const handleRemoveGcp = (idx: number) => {
    const updated = gcps.filter((_, i) => i !== idx);
    setGcps(updated);
    if (currentJobId && updated.length >= 3) {
      api.calibrateWithGCPs(currentJobId, updated).catch(console.error);
    }
  };

  // Filter datasets
  const userDatasets = datasets.filter((d) => d.source === 'user_upload');
  const preloadedDatasets = datasets.filter((d) => d.source === 'preloaded');
  const filteredDatasets =
    filterTab === 'user'
      ? userDatasets
      : filterTab === 'preloaded'
      ? preloadedDatasets
      : datasets;

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
          <span>Satellite Imagery Ingestion & Dataset Library</span>
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          Unified remote-sensing repository. Select from preloaded ISRO benchmark missions or upload custom optical imagery (GeoTIFF, PNG, JPG).
        </p>
      </div>

      {errorMsg && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between shadow-lg">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>{errorMsg}</span>
          </div>
          <button onClick={() => setErrorMsg(null)} className="text-rose-400 hover:text-white font-bold text-sm">
            ✕
          </button>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SECTION 1: UNIFIED DATASET LIBRARY / ARCHIVE BROWSER                     */}
      {/* ========================================================================= */}
      <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4 shadow-xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-2.5">
            <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
              <Database className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs font-mono font-bold text-slate-200 tracking-wider uppercase">
                Dataset Library & Archive
              </div>
              <div className="text-[11px] text-slate-400">
                {datasets.length} total datasets ({userDatasets.length} user uploads, {preloadedDatasets.length} preloaded)
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            {/* Filter Tabs */}
            <div className="flex rounded-lg bg-slate-950 p-1 border border-slate-800 text-[11px] font-mono">
              <button
                onClick={() => setFilterTab('all')}
                className={`px-3 py-1 rounded-md transition-all ${
                  filterTab === 'all'
                    ? 'bg-cyan-500 text-black font-bold shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                All ({datasets.length})
              </button>
              <button
                onClick={() => setFilterTab('user')}
                className={`px-3 py-1 rounded-md transition-all ${
                  filterTab === 'user'
                    ? 'bg-cyan-500 text-black font-bold shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                User Uploads ({userDatasets.length})
              </button>
              <button
                onClick={() => setFilterTab('preloaded')}
                className={`px-3 py-1 rounded-md transition-all ${
                  filterTab === 'preloaded'
                    ? 'bg-cyan-500 text-black font-bold shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                Preloaded ({preloadedDatasets.length})
              </button>
            </div>

            {/* Refresh Button */}
            <button
              onClick={() => refreshDatasets()}
              disabled={isLoadingDatasets}
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
              title="Refresh library"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoadingDatasets ? 'animate-spin text-cyan-400' : ''}`} />
            </button>
          </div>
        </div>

        {/* Dataset Cards Grid */}
        {filteredDatasets.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredDatasets.map((ds) => {
              const isSelected = activeDatasetId === ds.id;
              const has3D = ds.latest_results || ds.status === 'completed' || (isSelected && Boolean(results));

              return (
                <div
                  key={ds.id}
                  onClick={() => handleSelectDataset(ds.id)}
                  className={`group relative rounded-xl border p-3.5 transition-all cursor-pointer flex flex-col justify-between ${
                    isSelected
                      ? 'bg-cyan-500/10 border-cyan-500/80 shadow-lg shadow-cyan-500/10 ring-1 ring-cyan-500/40'
                      : 'bg-slate-950/60 border-slate-800/90 hover:border-slate-700 hover:bg-slate-900/60'
                  }`}
                >
                  {/* Top Thumbnail & Badges */}
                  <div className="space-y-2.5">
                    <div className="relative h-32 w-full overflow-hidden rounded-lg bg-slate-950 border border-slate-800/80">
                      <img
                        src={ds.thumbnail_url}
                        alt={ds.name}
                        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                        onError={(e) => {
                          (e.target as HTMLElement).style.opacity = '0.3';
                        }}
                      />
                      {/* Top Left: Source Pill */}
                      <span
                        className={`absolute top-2 left-2 px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase tracking-wider backdrop-blur-md shadow-sm ${
                          ds.source === 'user_upload'
                            ? 'bg-cyan-950/90 text-cyan-300 border border-cyan-500/40'
                            : 'bg-indigo-950/90 text-indigo-300 border border-indigo-500/40'
                        }`}
                      >
                        {ds.source === 'user_upload' ? 'User Upload' : 'Preloaded'}
                      </span>

                      {/* Top Right: GeoTIFF / Optical Pill */}
                      <span
                        className={`absolute top-2 right-2 px-1.5 py-0.5 rounded text-[9px] font-mono font-bold backdrop-blur-md shadow-sm ${
                          ds.georeferenced
                            ? 'bg-emerald-950/90 text-emerald-300 border border-emerald-500/40'
                            : 'bg-amber-950/90 text-amber-300 border border-amber-500/40'
                        }`}
                      >
                        {ds.georeferenced ? 'GeoTIFF (DSM)' : 'Optical (rDSM)'}
                      </span>

                      {/* Bottom Left: Dimensions Pill */}
                      <span className="absolute bottom-2 left-2 px-1.5 py-0.5 rounded text-[9px] font-mono bg-black/80 text-slate-300 border border-slate-700 backdrop-blur-md">
                        {ds.width} × {ds.height} px
                      </span>

                      {/* Bottom Right: Low Res Warning Pill */}
                      {ds.is_low_resolution && (
                        <span className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-rose-950/90 text-rose-300 border border-rose-500/40 backdrop-blur-md flex items-center gap-1">
                          <AlertTriangle className="w-2.5 h-2.5" />
                          Low-Res
                        </span>
                      )}
                    </div>

                    {/* Title & Metadata */}
                    <div>
                      <div className="flex items-center justify-between gap-2">
                        <h4
                          className="text-xs font-bold text-white group-hover:text-cyan-300 transition-colors truncate"
                          title={ds.name}
                        >
                          {ds.name}
                        </h4>
                        <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 shrink-0">
                          {ds.file_type}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 mt-1 text-[10px] font-mono text-slate-400">
                        <span className="truncate max-w-[140px]" title={ds.crs || 'Unavailable'}>
                          {ds.crs || 'Unavailable'}
                        </span>
                        {ds.has_dem && (
                          <span className="px-1 rounded bg-blue-500/15 text-blue-300 border border-blue-500/30 text-[9px]">
                            +DEM
                          </span>
                        )}
                        {ds.has_gcps && (
                          <span className="px-1 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 text-[9px]">
                            +GCPs
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Card Footer & Action Buttons */}
                  <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[10px] font-mono">
                    <div className="flex items-center space-x-1.5">
                      {has3D ? (
                        <span className="flex items-center text-emerald-400 font-bold gap-1">
                          <CheckCircle2 className="w-3 h-3" />
                          3D Ready
                        </span>
                      ) : ds.status === 'rejected' || ds.input_validation?.status === 'rejected' ? (
                        <span className="flex items-center text-rose-400 font-bold gap-1" title={ds.input_validation?.rejection_reason || 'Rejected by quality control'}>
                          <ShieldX className="w-3 h-3" />
                          Rejected
                        </span>
                      ) : ds.status === 'processing' ? (
                        <span className="flex items-center text-cyan-400 font-bold gap-1">
                          <RefreshCw className="w-3 h-3 animate-spin" />
                          Processing
                        </span>
                      ) : (
                        <span className="flex items-center text-slate-400 gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
                          Ready
                        </span>
                      )}
                    </div>

                    <div className="flex items-center space-x-2">
                      {ds.source === 'user_upload' && (
                        <button
                          onClick={(e) => handleDeleteDataset(e, ds)}
                          className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                          title="Delete user upload from disk"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}

                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold transition-all ${
                          isSelected
                            ? 'bg-cyan-500 text-black shadow-sm'
                            : 'text-cyan-400 group-hover:translate-x-0.5'
                        }`}
                      >
                        {isSelected ? 'ACTIVE' : 'Select →'}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="p-8 rounded-xl bg-slate-950/40 border border-dashed border-slate-800 text-center space-y-2">
            <FolderOpen className="w-8 h-8 text-slate-600 mx-auto" />
            <div className="text-xs font-mono text-slate-400">
              No datasets found under the "{filterTab}" category.
            </div>
            <p className="text-[11px] text-slate-400">
              Upload new imagery below to add to your user library.
            </p>
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* SECTION 2: WORKSPACE (INGESTION & ACTIVE DATASET INSPECTION)             */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (7 cols): Upload New Imagery & GCP Table */}
        <div className="lg:col-span-7 space-y-4">
          <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2">
                <UploadCloud className="w-4 h-4 text-cyan-400" />
                <h3 className="text-xs font-mono font-bold text-white uppercase tracking-wider">
                  Upload & Ingest New Imagery
                </h3>
              </div>
              <span className="text-[10px] font-mono text-slate-400">Persistent Disk Storage</span>
            </div>

            {/* Main Image Drop Area */}
            <div className="p-6 rounded-xl border-2 border-dashed border-slate-700/80 hover:border-cyan-500/50 bg-slate-950/40 text-center space-y-3 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 flex items-center justify-center mx-auto">
                <UploadCloud className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-white">Primary Optical Satellite/Aerial Imagery</h4>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  GeoTIFF (.tif, .tiff), PNG, JPG, JPEG (Max 100MB)
                </p>
              </div>

              <label className="inline-block cursor-pointer">
                <input
                  type="file"
                  accept=".tif,.tiff,.png,.jpg,.jpeg"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files?.[0]) {
                      setImageFile(e.target.files[0]);
                    }
                  }}
                />
                <span className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-medium transition-colors">
                  {imageFile ? 'Change File' : 'Browse Local Imagery'}
                </span>
              </label>

              {imageFile && (
                <div className="space-y-2 pt-1">
                  <div className="text-xs font-mono text-cyan-300">
                    Selected: {imageFile.name} ({(imageFile.size / 1024 / 1024).toFixed(2)} MB)
                  </div>

                  {isValidatingStaged && (
                    <div className="p-2.5 rounded-lg bg-slate-900 border border-cyan-500/30 text-xs font-mono flex items-center justify-center space-x-2 text-cyan-300">
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Inspecting optical remote-sensing suitability...</span>
                    </div>
                  )}

                  {stagedValidation && !isValidatingStaged && (
                    <div className={`p-3 rounded-lg border text-left text-xs font-mono space-y-2.5 ${
                      stagedValidation.status === 'rejected'
                        ? 'bg-rose-500/10 border-rose-500/40 text-rose-300'
                        : stagedValidation.status === 'warning'
                        ? 'bg-amber-500/10 border-amber-500/40 text-amber-300'
                        : 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300'
                    }`}>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          {stagedValidation.status === 'rejected' ? (
                            <ShieldX className="w-4 h-4 text-rose-400" />
                          ) : stagedValidation.status === 'warning' ? (
                            <ShieldAlert className="w-4 h-4 text-amber-400" />
                          ) : (
                            <ShieldCheck className="w-4 h-4 text-emerald-400" />
                          )}
                          <span className="font-bold uppercase tracking-wider text-[11px]">
                            {stagedValidation.status === 'rejected'
                              ? 'Input Incompatible: Rejected'
                              : stagedValidation.status === 'warning'
                              ? 'Advisory Notice'
                              : 'Suitability Verified'}
                          </span>
                        </div>
                        <span className="px-2 py-0.5 rounded bg-black/50 text-[10px] font-bold">
                          Suitability: {stagedValidation.suitability_score}%
                        </span>
                      </div>

                      <div className="text-[11px] space-y-1">
                        <div>
                          <span className="text-slate-400">Detected:</span>{' '}
                          <span className="font-semibold text-white uppercase">{stagedValidation.detected_content.replace(/_/g, ' ')}</span>
                        </div>
                        {stagedValidation.rejection_reason && (
                          <div className="text-rose-300 leading-snug">
                            {stagedValidation.rejection_reason}
                          </div>
                        )}
                      </div>

                      {stagedValidation.status === 'rejected' && (
                        <div className="pt-1 flex items-center justify-between">
                          <span className="text-[10px] text-slate-400">
                            Satellite/aerial/drone imagery required.
                          </span>
                          <button
                            type="button"
                            onClick={() => {
                              setImageFile(null);
                              setStagedValidation(null);
                            }}
                            className="px-2.5 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white font-bold text-[10px] transition-colors"
                          >
                            Choose Another Image
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Optional Secondary Inputs */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* DEM Attachment */}
              <div className="p-3.5 rounded-xl bg-slate-950/50 border border-slate-800 space-y-1.5">
                <div className="flex items-center space-x-1.5 text-xs font-semibold text-slate-200">
                  <Globe className="w-3.5 h-3.5 text-blue-400" />
                  <span>Reference DEM (Optional)</span>
                </div>
                <p className="text-[10px] text-slate-400">
                  SRTM or CartoDEM GeoTIFF for metric elevation scaling.
                </p>
                <label className="inline-block cursor-pointer pt-1">
                  <input
                    type="file"
                    accept=".tif,.tiff"
                    className="hidden"
                    onChange={(e) => e.target.files?.[0] && setDemFile(e.target.files[0])}
                  />
                  <span className="px-2.5 py-1 rounded bg-slate-800 text-slate-300 text-[11px] hover:bg-slate-700 border border-slate-700">
                    {demFile ? demFile.name : 'Attach DEM (.tif)'}
                  </span>
                </label>
              </div>

              {/* GCP Attachment */}
              <div className="p-3.5 rounded-xl bg-slate-950/50 border border-slate-800 space-y-1.5">
                <div className="flex items-center space-x-1.5 text-xs font-semibold text-slate-200">
                  <Layers className="w-3.5 h-3.5 text-amber-400" />
                  <span>Ground Control Points (Optional)</span>
                </div>
                <p className="text-[10px] text-slate-400">
                  CSV formatted as: id, easting, northing, elevation.
                </p>
                <label className="inline-block cursor-pointer pt-1">
                  <input
                    type="file"
                    accept=".csv,.txt"
                    className="hidden"
                    onChange={(e) => e.target.files?.[0] && setGcpFile(e.target.files[0])}
                  />
                  <span className="px-2.5 py-1 rounded bg-slate-800 text-slate-300 text-[11px] hover:bg-slate-700 border border-slate-700">
                    {gcpFile ? gcpFile.name : 'Attach GCP CSV (.csv)'}
                  </span>
                </label>
              </div>
            </div>

            {/* Upload Action Button */}
            {imageFile && (
              <button
                onClick={handleUploadDataset}
                disabled={isUploading}
                className="w-full py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-black font-bold text-xs font-mono transition-all shadow-lg shadow-cyan-500/20 flex items-center justify-center space-x-2"
              >
                {isUploading ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Ingesting & Persisting to Library...</span>
                  </>
                ) : (
                  <>
                    <UploadCloud className="w-3.5 h-3.5" />
                    <span>Upload & Add to Dataset Library</span>
                  </>
                )}
              </button>
            )}
          </div>

          {/* Interactive GCP Management Table */}
          {gcps.length > 0 && (
            <div className="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <div className="flex items-center space-x-2 text-xs font-mono font-bold text-amber-400">
                  <Table className="w-4 h-4" />
                  <span>GROUND CONTROL POINTS ({gcps.length} PTS)</span>
                </div>
                <span className="text-[10px] font-mono text-slate-400">Huber Linear Regression</span>
              </div>

              <div className="max-h-40 overflow-y-auto">
                <table className="w-full text-left font-mono text-[11px]">
                  <thead>
                    <tr className="text-slate-400 border-b border-slate-800">
                      <th className="py-1">ID</th>
                      <th className="py-1">X / Easting</th>
                      <th className="py-1">Y / Northing</th>
                      <th className="py-1">Elev (m)</th>
                      <th className="py-1 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gcps.map((gcp, idx) => (
                      <tr key={idx} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                        <td className="py-1 font-semibold text-white">{gcp.id}</td>
                        <td className="py-1 text-slate-300">{gcp.x.toFixed(1)}</td>
                        <td className="py-1 text-slate-300">{gcp.y.toFixed(1)}</td>
                        <td className="py-1 text-cyan-300 font-bold">{gcp.elevation.toFixed(1)}</td>
                        <td className="py-1 text-right">
                          <button
                            onClick={() => handleRemoveGcp(idx)}
                            className="text-slate-500 hover:text-rose-400 transition-colors"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Add GCP inline */}
              <div className="pt-2 border-t border-slate-800 flex items-center gap-2 text-xs font-mono">
                <input
                  type="text"
                  placeholder="ID"
                  value={newGcpId}
                  onChange={(e) => setNewGcpId(e.target.value)}
                  className="w-16 px-2 py-1 rounded bg-slate-950 border border-slate-700 text-white text-[11px]"
                />
                <input
                  type="number"
                  placeholder="X / East"
                  value={newGcpX}
                  onChange={(e) => setNewGcpX(e.target.value)}
                  className="w-24 px-2 py-1 rounded bg-slate-950 border border-slate-700 text-white text-[11px]"
                />
                <input
                  type="number"
                  placeholder="Y / North"
                  value={newGcpY}
                  onChange={(e) => setNewGcpY(e.target.value)}
                  className="w-24 px-2 py-1 rounded bg-slate-950 border border-slate-700 text-white text-[11px]"
                />
                <input
                  type="number"
                  placeholder="Elev"
                  value={newGcpElev}
                  onChange={(e) => setNewGcpElev(e.target.value)}
                  className="w-16 px-2 py-1 rounded bg-slate-950 border border-slate-700 text-white text-[11px]"
                />
                <button
                  onClick={handleAddGcp}
                  className="px-2.5 py-1 rounded bg-amber-500 hover:bg-amber-400 text-black font-bold text-[11px] flex items-center gap-1 transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  <span>Add</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Right Column (5 cols): Active Dataset Spatial Inspector & Execution */}
        <div className="lg:col-span-5 space-y-4">
          {activeDataset ? (
            <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-4 shadow-xl">
              {/* Header */}
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center space-x-2">
                  <Eye className="w-4 h-4 text-cyan-400" />
                  <h3 className="text-xs font-mono font-bold text-slate-200 uppercase">
                    Active Dataset Inspector
                  </h3>
                </div>
                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                    activeDataset.georeferenced
                      ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                      : 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                  }`}
                >
                  {activeDataset.georeferenced ? 'GEOREFERENCED (DSM)' : 'RELATIVE (rDSM)'}
                </span>
              </div>

              {/* Real Visual Preview of Selected Dataset */}
              <div className="relative rounded-xl overflow-hidden bg-slate-950 border border-slate-800 max-h-52">
                <img
                  src={activeDataset.preview_url}
                  alt={activeDataset.name}
                  className="w-full h-52 object-cover"
                  onError={(e) => {
                    (e.target as HTMLImageElement).src = activeDataset.thumbnail_url;
                  }}
                />
                <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-transparent to-transparent pointer-events-none" />
                <div className="absolute bottom-2 left-3 right-3 flex items-center justify-between text-[11px] font-mono">
                  <span className="text-white font-bold truncate max-w-[200px]" title={activeDataset.name}>
                    {activeDataset.name}
                  </span>
                  <span className="px-2 py-0.5 rounded bg-black/80 backdrop-blur-md text-cyan-300 border border-slate-700 text-[10px]">
                    {activeDataset.width} × {activeDataset.height} px
                  </span>
                </div>
              </div>

              {/* Critical Low-Resolution Warning Banner */}
              {activeDataset.is_low_resolution && (
                <div className={`p-3 rounded-xl border text-xs font-mono flex items-start gap-2.5 ${
                  activeDataset.width < 64 || activeDataset.height < 64
                    ? 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                    : 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                }`}>
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-400" />
                  <div className="space-y-1">
                    <div className="font-bold text-[11px] uppercase tracking-wide">
                      {activeDataset.width < 64 || activeDataset.height < 64 ? 'Critical Low-Resolution Warning' : 'Sub-Optimal Resolution Advisory'}
                    </div>
                    <div className="text-[11px] leading-relaxed text-slate-300">
                      {activeDataset.resolution_warning || `Image is ${activeDataset.width}×${activeDataset.height} px.`}
                    </div>
                    <div className="text-[10px] text-slate-400 pt-0.5">
                      Recommended input size: <span className="text-cyan-300 font-semibold">≥ 512 × 512 px</span>. Output will be generated in preview-only mode with cubic interpolation.
                    </div>
                  </div>
                </div>
              )}

              {/* Optical Remote-Sensing Quality Control Card */}
              {activeDataset.input_validation && (
                <div className={`p-4 rounded-xl border text-xs font-mono space-y-3 ${
                  activeDataset.status === 'rejected' || activeDataset.input_validation.status === 'rejected'
                    ? 'bg-rose-500/10 border-rose-500/40 text-rose-300'
                    : activeDataset.input_validation.status === 'warning'
                    ? 'bg-amber-500/10 border-amber-500/40 text-amber-300'
                    : 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300'
                }`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      {activeDataset.status === 'rejected' || activeDataset.input_validation.status === 'rejected' ? (
                        <ShieldX className="w-4 h-4 text-rose-400" />
                      ) : activeDataset.input_validation.status === 'warning' ? (
                        <ShieldAlert className="w-4 h-4 text-amber-400" />
                      ) : (
                        <ShieldCheck className="w-4 h-4 text-emerald-400" />
                      )}
                      <span className="font-bold uppercase tracking-wider text-[11px]">
                        {activeDataset.status === 'rejected' || activeDataset.input_validation.status === 'rejected'
                          ? 'REJECTED / INCOMPATIBLE'
                          : activeDataset.input_validation.status === 'warning'
                          ? 'QUALITY ADVISORY'
                          : 'VERIFIED REMOTE-SENSING'}
                      </span>
                    </div>

                    <div className="flex items-center space-x-2">
                      <span className="px-2 py-0.5 rounded bg-black/60 text-[10px] font-bold">
                        Suitability: {activeDataset.input_validation.suitability_score}%
                      </span>
                    </div>
                  </div>

                  {/* Suitability Meter */}
                  <div className="w-full bg-slate-950 rounded-full h-1.5 overflow-hidden border border-slate-800">
                    <div
                      className={`h-full transition-all duration-500 ${
                        activeDataset.input_validation.suitability_score >= 70
                          ? 'bg-gradient-to-r from-emerald-500 to-cyan-400'
                          : activeDataset.input_validation.suitability_score >= 40
                          ? 'bg-gradient-to-r from-amber-500 to-yellow-400'
                          : 'bg-gradient-to-r from-rose-600 to-rose-400'
                      }`}
                      style={{ width: `${Math.max(5, activeDataset.input_validation.suitability_score)}%` }}
                    />
                  </div>

                  <div className="text-[11px] text-slate-300 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Detected Content Category:</span>
                      <span className="font-bold text-white uppercase text-[10px] px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700">
                        {activeDataset.input_validation.detected_content.replace(/_/g, ' ')}
                      </span>
                    </div>

                    {activeDataset.input_validation.rejection_reason && (
                      <div className="p-2.5 rounded-lg bg-rose-950/40 border border-rose-500/30 text-rose-300 text-[11px] leading-relaxed mt-2 space-y-1.5">
                        <div className="font-bold uppercase text-[10px] flex items-center gap-1.5 text-rose-400">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          <span>Quality Control Rejection Reason</span>
                        </div>
                        <p>{activeDataset.input_validation.rejection_reason}</p>
                        <p className="text-slate-400 text-[10px]">
                          DepthWizard reconstructs 3D surfaces from <strong>satellite, aerial, drone, and terrain imagery</strong>. Human portraits, product close-ups, code screenshots, and documents are rejected to prevent scientifically invalid depth models.
                        </p>
                        <div className="pt-1">
                          <button
                            onClick={() => handleSelectDataset('himalayan_valley')}
                            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-cyan-300 text-[10px] font-bold border border-slate-700 transition-colors"
                          >
                            Switch to ISRO Benchmark Mission →
                          </button>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Expandable 6-Stage Checklist */}
                  <div className="pt-2 border-t border-slate-800/80">
                    <button
                      type="button"
                      onClick={() => setShowActiveStages(!showActiveStages)}
                      className="w-full flex items-center justify-between text-[10px] text-slate-400 hover:text-slate-200 transition-colors uppercase font-bold"
                    >
                      <span>Quality Control Checklist ({activeDataset.input_validation.stages.filter(s => s.passed).length}/6 Passed)</span>
                      {showActiveStages ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>

                    {showActiveStages && (
                      <div className="mt-2 space-y-1.5 pt-1">
                        {activeDataset.input_validation.stages.map((stage) => (
                          <div key={stage.stage_id} className="p-2 rounded bg-black/40 border border-slate-800 text-[10px] flex items-start justify-between gap-2">
                            <div className="flex items-start space-x-1.5">
                              {stage.passed ? (
                                <Check className="w-3 h-3 text-emerald-400 shrink-0 mt-0.5" />
                              ) : stage.warning ? (
                                <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0 mt-0.5" />
                              ) : (
                                <XCircle className="w-3 h-3 text-rose-400 shrink-0 mt-0.5" />
                              )}
                              <div>
                                <span className="font-bold text-white">{stage.name}: </span>
                                <span className="text-slate-300">{stage.message}</span>
                              </div>
                            </div>
                            <span className={`px-1.5 py-0.5 rounded text-[9px] uppercase font-bold shrink-0 ${
                              stage.passed ? 'bg-emerald-950 text-emerald-300 border border-emerald-500/30' :
                              stage.warning ? 'bg-amber-950 text-amber-300 border border-amber-500/30' :
                              'bg-rose-950 text-rose-300 border border-rose-500/30'
                            }`}>
                              {stage.passed ? 'Passed' : stage.warning ? 'Warning' : 'Failed'}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Metadata List */}
              <div className="space-y-2 text-xs font-mono">
                <div className="flex items-center justify-between py-1 border-b border-slate-800/60">
                  <span className="text-slate-400">Dataset Source</span>
                  <span className={`font-semibold ${activeDataset.source === 'user_upload' ? 'text-cyan-300' : 'text-indigo-300'}`}>
                    {activeDataset.source === 'user_upload' ? 'User Upload' : 'ISRO Benchmark Mission'}
                  </span>
                </div>

                <div className="flex items-center justify-between py-1 border-b border-slate-800/60">
                  <span className="text-slate-400">Filename</span>
                  <span className="text-white truncate max-w-[170px]" title={activeDataset.original_filename}>
                    {activeDataset.original_filename}
                  </span>
                </div>

                {activeDataset.classification && (
                  <div className="flex items-center justify-between py-1 border-b border-slate-800/60">
                    <span className="text-slate-400">Classification</span>
                    <span className="text-cyan-300 font-semibold">
                      {activeDataset.classification}
                    </span>
                  </div>
                )}

                <div className="flex items-center justify-between py-1 border-b border-slate-800/60">
                  <span className="text-slate-400">Format / Data Type</span>
                  <span className="text-slate-200 uppercase">
                    {activeDataset.file_type} ({activeDataset.dtype || 'uint8'})
                  </span>
                </div>

                <div className="flex items-center justify-between py-1 border-b border-slate-800/60">
                  <span className="text-slate-400">Dimensions / Bands</span>
                  <span className={`font-semibold ${activeDataset.is_low_resolution ? 'text-amber-400' : 'text-slate-200'}`}>
                    {activeDataset.width} × {activeDataset.height} px ({activeDataset.channels} bands)
                  </span>
                </div>

                <div className="flex items-center justify-between py-1 border-b border-slate-800/60">
                  <span className="text-slate-400">Coordinate Reference (CRS)</span>
                  <span className="text-cyan-300 truncate max-w-[170px]" title={activeDataset.crs || 'Unavailable'}>
                    {activeDataset.crs || 'Unavailable'}
                  </span>
                </div>

                <div className="flex items-center justify-between py-1 border-b border-slate-800/60">
                  <span className="text-slate-400">Pixel Resolution</span>
                  <span className="text-slate-200">
                    {activeDataset.resolution
                      ? `${activeDataset.resolution[0].toFixed(2)}m × ${activeDataset.resolution[1].toFixed(2)}m`
                      : 'Unavailable'}
                  </span>
                </div>

                {activeDataset.bounds && (
                  <div className="text-[10px] text-slate-400 py-1 border-b border-slate-800/60 space-y-0.5">
                    <div>Bounds: [{activeDataset.bounds.map((b) => b.toFixed(1)).join(', ')}]</div>
                  </div>
                )}

                <div className="flex items-center justify-between py-1">
                  <span className="text-slate-400">Target Output Mode</span>
                  <span className="text-cyan-400 font-bold">
                    {activeDataset.georeferenced ? 'Absolute DSM (Meters)' : 'Relative DSM (rDSM)'}
                  </span>
                </div>
              </div>

              {/* Attached DEM Card if present */}
              {activeDataset.has_dem && activeDataset.dem_metadata && (
                <div className="p-3 rounded-xl bg-slate-950/60 border border-blue-500/30 text-xs font-mono space-y-1.5">
                  <div className="flex items-center justify-between text-blue-400 font-bold">
                    <div className="flex items-center gap-1.5">
                      <Globe className="w-3.5 h-3.5" />
                      <span>ATTACHED REFERENCE DEM</span>
                    </div>
                    <span className="text-[10px] text-emerald-400">VERIFIED</span>
                  </div>
                  <div className="text-[11px] text-slate-300">
                    {activeDataset.dem_metadata.filename} ({activeDataset.dem_metadata.min_elevation}m – {activeDataset.dem_metadata.max_elevation}m)
                  </div>
                </div>
              )}

              {/* Execution CTA Buttons */}
              {results && !isProcessing ? (
                <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs space-y-2">
                  <div className="flex items-center space-x-2 font-bold">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>Reconstruction Ready & Active!</span>
                  </div>
                  <p className="text-[11px] text-emerald-400/80">
                    Terrain mesh and Digital Surface Model generated for this dataset.
                  </p>
                  <div className="grid grid-cols-2 gap-2 pt-1">
                    <button
                      onClick={() => setActiveTab('explorer')}
                      className="py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black font-bold text-xs font-mono flex items-center justify-center space-x-1.5 transition-colors shadow-md shadow-emerald-500/20"
                    >
                      <span>3D Explorer</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={handleStartReconstruction}
                      className="py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium text-xs font-mono flex items-center justify-center space-x-1.5 transition-colors"
                    >
                      <RefreshCw className="w-3 h-3" />
                      <span>Re-run 3D</span>
                    </button>
                  </div>
                </div>
              ) : (activeDataset.status === 'rejected' || activeDataset.input_validation?.status === 'rejected') ? (
                <button
                  disabled
                  className="w-full py-3 rounded-xl bg-slate-900 border border-rose-500/40 text-rose-400 font-bold text-xs font-mono uppercase tracking-wider cursor-not-allowed flex items-center justify-center space-x-2 shadow-inner opacity-90"
                  title={activeDataset.input_validation?.rejection_reason || 'Reconstruction blocked for rejected imagery'}
                >
                  <ShieldX className="w-4 h-4 text-rose-400" />
                  <span>Reconstruction Blocked (Quality Control)</span>
                </button>
              ) : !isProcessing ? (
                <button
                  onClick={handleStartReconstruction}
                  className="w-full py-3 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 text-black font-semibold text-xs font-mono uppercase tracking-wider hover:from-cyan-400 hover:to-blue-500 transition-all shadow-lg shadow-cyan-500/25 flex items-center justify-center space-x-2"
                >
                  <Play className="w-4 h-4 fill-black" />
                  <span>Execute 3D Reconstruction</span>
                </button>
              ) : null}
            </div>
          ) : (
            <div className="p-8 rounded-2xl bg-slate-900/40 border border-slate-800 text-center space-y-3">
              <Globe className="w-8 h-8 text-slate-500 mx-auto" />
              <h4 className="text-xs font-mono uppercase text-slate-300">Awaiting Active Dataset</h4>
              <p className="text-xs text-slate-400 leading-relaxed">
                Select a dataset from the library above or upload custom imagery to inspect geospatial parameters.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Real-time Processing Stage Timeline */}
      {isProcessing && jobStatus && (
        <div className="p-6 rounded-2xl bg-slate-900/90 border border-cyan-500/40 space-y-6 shadow-2xl shadow-cyan-500/10">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center">
                <RefreshCw className="w-4 h-4 text-cyan-400 animate-spin" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white font-mono">
                  RECONSTRUCTION IN PROGRESS
                </h3>
                <p className="text-xs text-cyan-400 font-mono">{jobStatus.message}</p>
              </div>
            </div>
            <div className="text-right font-mono">
              <div className="text-xl font-bold text-cyan-300">{jobStatus.progress}%</div>
              <div className="text-[10px] text-slate-400">Total Progress</div>
            </div>
          </div>

          {/* Master Progress Bar */}
          <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 transition-all duration-300"
              style={{ width: `${jobStatus.progress}%` }}
            />
          </div>

          {/* 8 Standardized Operational Stages */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 pt-2">
            {jobStatus.stages.map((stage) => {
              const isDone = stage.is_done;
              const isCurr = stage.is_current;

              return (
                <div
                  key={stage.stage_id}
                  className={`p-3 rounded-xl border text-xs font-mono transition-all ${
                    isCurr
                      ? 'bg-cyan-500/10 border-cyan-500 text-cyan-300 shadow-sm shadow-cyan-500/20'
                      : isDone
                      ? 'bg-slate-900 border-emerald-500/40 text-slate-300'
                      : 'bg-slate-950/40 border-slate-800/60 text-slate-400'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] uppercase text-slate-400">{stage.stage_id}</span>
                    {isDone ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    ) : isCurr ? (
                      <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
                    ) : (
                      <span className="w-2 h-2 rounded-full bg-slate-700" />
                    )}
                  </div>
                  <div className="font-semibold text-[11px] truncate">{stage.name}</div>
                  <div className="text-[10px] text-slate-400 mt-1 truncate">{stage.message}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
