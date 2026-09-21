import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { JobStatus, ReconstructionSummary, EvaluationResponse, DatasetSummary, DatasetListResponse } from '../types';
import { api } from '../services/api';

export type NavTab = 
  | 'landing'
  | 'upload'
  | 'depth'
  | 'dsm'
  | 'explorer'
  | 'analysis'
  | 'validation'
  | 'methodology';

interface ProjectContextType {
  activeTab: NavTab;
  setActiveTab: (tab: NavTab) => void;
  datasets: DatasetSummary[];
  activeDatasetId: string | null;
  activeDataset: DatasetSummary | null;
  isLoadingDatasets: boolean;
  currentJobId: string | null;
  setCurrentJobId: (id: string | null) => void;
  jobStatus: JobStatus | null;
  setJobStatus: (status: JobStatus | null) => void;
  results: ReconstructionSummary | null;
  setResults: (results: ReconstructionSummary | null) => void;
  evaluation: EvaluationResponse | null;
  setEvaluation: (evaluation: EvaluationResponse | null) => void;
  deviceInfo: { device: string; isFallback: boolean } | null;
  loadJobResults: (jobId: string) => Promise<void>;
  resetProject: () => void;
  isExportOpen: boolean;
  setIsExportOpen: (open: boolean) => void;
  selectDataset: (id: string) => Promise<void>;
  uploadDataset: (imageFile: File, demFile?: File | null, gcpFile?: File | null) => Promise<DatasetSummary>;
  deleteDataset: (id: string) => Promise<void>;
  refreshDatasets: () => Promise<DatasetListResponse>;
}

const STORAGE_KEY_ACTIVE_DATASET = 'depthwizard_active_dataset_id';

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

export const ProjectProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [activeTab, setActiveTab] = useState<NavTab>('landing');
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [activeDatasetId, setActiveDatasetId] = useState<string | null>(null);
  const [isLoadingDatasets, setIsLoadingDatasets] = useState<boolean>(true);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [results, setResults] = useState<ReconstructionSummary | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationResponse | null>(null);
  const [deviceInfo, setDeviceInfo] = useState<{ device: string; isFallback: boolean } | null>(null);
  const [isExportOpen, setIsExportOpen] = useState<boolean>(false);

  const activeDataset = datasets.find((d) => d.id === activeDatasetId) || null;

  const loadJobResults = useCallback(async (jobId: string) => {
    try {
      const summary = await api.getResults(jobId);
      setResults(summary);
      setCurrentJobId(jobId);
      try {
        const evalData = await api.getEvaluation(jobId);
        setEvaluation(evalData);
      } catch (e) {
        console.warn('Evaluation not available yet:', e);
      }
    } catch (err) {
      console.error(`Failed to load results for job ${jobId}:`, err);
    }
  }, []);

  const selectDataset = useCallback(async (id: string) => {
    try {
      const selected = await api.selectDataset(id);
      setActiveDatasetId(id);
      localStorage.setItem(STORAGE_KEY_ACTIVE_DATASET, id);

      // Restore results if dataset already processed
      if (selected.latest_results) {
        setResults(selected.latest_results);
        setCurrentJobId(selected.active_job_id || selected.latest_results.job_id);
      } else if (selected.active_job_id) {
        try {
          const summary = await api.getResults(selected.active_job_id);
          setResults(summary);
          setCurrentJobId(selected.active_job_id);
        } catch {
          setResults(null);
          setCurrentJobId(selected.active_job_id);
        }
      } else {
        setResults(null);
        setCurrentJobId(null);
        setJobStatus(null);
      }
    } catch (err) {
      console.error(`Failed to select dataset ${id}:`, err);
    }
  }, []);

  const refreshDatasets = useCallback(async (): Promise<DatasetListResponse> => {
    try {
      const resp = await api.getDatasets();
      setDatasets(resp.datasets);
      return resp;
    } catch (err) {
      console.error('Failed to refresh datasets:', err);
      throw err;
    }
  }, []);

  const uploadDataset = async (imageFile: File, demFile?: File | null, gcpFile?: File | null): Promise<DatasetSummary> => {
    const newDs = await api.uploadDataset(imageFile, demFile, gcpFile);
    await refreshDatasets();
    await selectDataset(newDs.id);
    return newDs;
  };

  const deleteDataset = async (id: string): Promise<void> => {
    const res = await api.deleteDataset(id);
    const resp = await refreshDatasets();
    if (activeDatasetId === id) {
      const nextId = res.active_dataset_id || resp.datasets[0]?.id;
      if (nextId) {
        await selectDataset(nextId);
      } else {
        setActiveDatasetId(null);
        setResults(null);
        setCurrentJobId(null);
      }
    }
  };

  // Initial load
  useEffect(() => {
    api.getHealth()
      .then((data) => {
        setDeviceInfo({
          device: data.device || 'CPU',
          isFallback: Boolean(data.is_fallback_mode)
        });
      })
      .catch((err) => console.warn('Could not fetch backend health:', err));

    setIsLoadingDatasets(true);
    api.getDatasets()
      .then(async (resp) => {
        setDatasets(resp.datasets);
        const savedId = localStorage.getItem(STORAGE_KEY_ACTIVE_DATASET);
        const validId = resp.datasets.find((d) => d.id === savedId)
          ? savedId
          : resp.active_dataset_id && resp.datasets.find((d) => d.id === resp.active_dataset_id)
          ? resp.active_dataset_id
          : resp.datasets[0]?.id;

        if (validId) {
          await selectDataset(validId);
        }
      })
      .catch((err) => console.error('Failed to load initial datasets:', err))
      .finally(() => setIsLoadingDatasets(false));
  }, [selectDataset]);

  const resetProject = () => {
    setCurrentJobId(null);
    setJobStatus(null);
    setResults(null);
    setEvaluation(null);
    setActiveTab('upload');
  };

  return (
    <ProjectContext.Provider
      value={{
        activeTab,
        setActiveTab,
        datasets,
        activeDatasetId,
        activeDataset,
        isLoadingDatasets,
        currentJobId,
        setCurrentJobId,
        jobStatus,
        setJobStatus,
        results,
        setResults,
        evaluation,
        setEvaluation,
        deviceInfo,
        loadJobResults,
        resetProject,
        isExportOpen,
        setIsExportOpen,
        selectDataset,
        uploadDataset,
        deleteDataset,
        refreshDatasets
      }}
    >
      {children}
    </ProjectContext.Provider>
  );
};

export const useProject = () => {
  const context = useContext(ProjectContext);
  if (!context) {
    throw new Error('useProject must be used within a ProjectProvider');
  }
  return context;
};
