import {
  JobStatus,
  ReconstructionSummary,
  EvaluationResponse,
  SampleDataset,
  TerrainProfileResponse,
  FloodSimulationResponse,
  GCPItem,
  HeightfieldData,
  DatasetSummary,
  DatasetListResponse,
  InputValidationResult,
  PointInspectionResult
} from '../types';

const API_BASE = '/api';

export const api = {
  async getHealth() {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error('Backend health check failed');
    return res.json();
  },

  async getDatasets(): Promise<DatasetListResponse> {
    const res = await fetch(`${API_BASE}/datasets`);
    if (!res.ok) throw new Error('Failed to fetch datasets');
    return res.json();
  },

  async getDataset(id: string): Promise<DatasetSummary> {
    const res = await fetch(`${API_BASE}/datasets/${id}`);
    if (!res.ok) throw new Error(`Failed to fetch dataset ${id}`);
    return res.json();
  },

  async validateInput(imageFile: File): Promise<InputValidationResult> {
    const formData = new FormData();
    formData.append('image', imageFile);
    const res = await fetch(`${API_BASE}/datasets/validate`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Image validation inspection failed');
    }
    return res.json();
  },

  async uploadDataset(imageFile: File, demFile?: File | null, gcpFile?: File | null): Promise<DatasetSummary> {
    const formData = new FormData();
    formData.append('image', imageFile);
    if (demFile) formData.append('dem', demFile);
    if (gcpFile) formData.append('gcp', gcpFile);

    const res = await fetch(`${API_BASE}/datasets/upload`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to upload dataset');
    }
    return res.json();
  },

  async deleteDataset(id: string): Promise<{ success: boolean; message: string; active_dataset_id?: string }> {
    const res = await fetch(`${API_BASE}/datasets/${id}`, {
      method: 'DELETE'
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to delete dataset');
    }
    return res.json();
  },

  async selectDataset(id: string): Promise<DatasetSummary> {
    const res = await fetch(`${API_BASE}/datasets/${id}/select`, {
      method: 'POST'
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to select dataset');
    }
    return res.json();
  },

  async prepareJob(datasetId: string): Promise<{ job_id: string; dataset_id: string }> {
    const res = await fetch(`${API_BASE}/datasets/${datasetId}/prepare-job`, {
      method: 'POST'
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to prepare reconstruction job');
    }
    return res.json();
  },

  async processDataset(datasetId: string): Promise<ReconstructionSummary> {
    const res = await fetch(`${API_BASE}/reconstruction/process`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dataset_id: datasetId })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Reconstruction processing failed');
    }
    return res.json();
  },

  async getSamples(): Promise<SampleDataset[]> {
    const res = await fetch(`${API_BASE}/samples`);
    if (!res.ok) throw new Error('Failed to fetch sample datasets');
    return res.json();
  },

  async loadSample(sampleId: string) {
    const res = await fetch(`${API_BASE}/samples/${sampleId}/load`, {
      method: 'POST'
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to load sample dataset');
    }
    return res.json();
  },

  async uploadFiles(imageFile: File, demFile?: File | null, gcpFile?: File | null) {
    const formData = new FormData();
    formData.append('image', imageFile);
    if (demFile) formData.append('dem', demFile);
    if (gcpFile) formData.append('gcp', gcpFile);

    const res = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to upload files');
    }
    return res.json();
  },

  async createJob(payload: { dataset_id?: string; image_path?: string }): Promise<JobStatus> {
    const res = await fetch(`${API_BASE}/jobs/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to create reconstruction job');
    }
    return res.json();
  },

  async startJob(jobId: string): Promise<ReconstructionSummary> {
    const res = await fetch(`${API_BASE}/jobs/${jobId}/start`, {
      method: 'POST'
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to start reconstruction job');
    }
    return res.json();
  },

  async getJobStatus(jobId: string): Promise<JobStatus> {
    const res = await fetch(`${API_BASE}/jobs/${jobId}`);
    if (!res.ok) throw new Error(`Failed to fetch job ${jobId}`);
    return res.json();
  },

  async startProcessing(jobId: string): Promise<ReconstructionSummary> {
    const res = await fetch(`${API_BASE}/process/${jobId}`, {
      method: 'POST'
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Reconstruction processing failed');
    }
    return res.json();
  },

  async getResults(jobId: string): Promise<ReconstructionSummary> {
    const res = await fetch(`${API_BASE}/results/${jobId}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to fetch reconstruction results');
    }
    return res.json();
  },

  async getDepthAssets(jobId: string) {
    const res = await fetch(`${API_BASE}/results/${jobId}/depth`);
    if (!res.ok) throw new Error('Failed to fetch depth assets');
    return res.json();
  },

  async getDSMAssets(jobId: string) {
    const res = await fetch(`${API_BASE}/results/${jobId}/dsm`);
    if (!res.ok) throw new Error('Failed to fetch DSM assets');
    return res.json();
  },

  async getArtifacts(jobId: string): Promise<{ job_id: string; artifacts: Record<string, string> }> {
    const res = await fetch(`${API_BASE}/results/${jobId}/artifacts`);
    if (!res.ok) throw new Error('Failed to fetch job artifacts');
    return res.json();
  },

  async getMeshAssets(jobId: string, quality: 'low' | 'medium' | 'high' = 'high') {
    const res = await fetch(`${API_BASE}/results/${jobId}/mesh?quality=${quality}`);
    if (!res.ok) throw new Error('Failed to fetch mesh assets');
    return res.json();
  },

  async getHeightfield(url: string): Promise<HeightfieldData> {
    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to load heightfield mesh data');
    return res.json();
  },

  async getTerrainProfile(
    jobId: string,
    transect: { x1_pct: number; y1_pct: number; x2_pct: number; y2_pct: number; samples?: number }
  ): Promise<TerrainProfileResponse> {
    const res = await fetch(`${API_BASE}/analysis/profile/${jobId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(transect)
    });
    if (!res.ok) throw new Error('Failed to compute terrain profile');
    return res.json();
  },

  async simulateFlood(jobId: string, waterElevation: number): Promise<FloodSimulationResponse> {
    const res = await fetch(`${API_BASE}/analysis/flood/${jobId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ water_elevation: waterElevation })
    });
    if (!res.ok) throw new Error('Flood simulation failed');
    return res.json();
  },

  async evaluateDSM(
    jobId: string,
    referenceFile: File,
    options?: { profile?: string; selectedMetrics?: string[] }
  ): Promise<EvaluationResponse> {
    const formData = new FormData();
    formData.append('reference_file', referenceFile);
    if (options?.profile) {
      formData.append('profile', options.profile);
    }
    if (options?.selectedMetrics && options.selectedMetrics.length > 0) {
      formData.append('selected_metrics', JSON.stringify(options.selectedMetrics));
    }

    const res = await fetch(`${API_BASE}/evaluate/${jobId}`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Evaluation failed');
    }
    return res.json();
  },

  async configureEvaluation(
    jobId: string,
    options: { profile?: string; selectedMetrics?: string[] }
  ): Promise<EvaluationResponse> {
    const res = await fetch(`${API_BASE}/evaluate/${jobId}/configure`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile: options.profile || 'terrain_standard',
        selected_metrics: options.selectedMetrics
      })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to reconfigure evaluation metrics');
    }
    return res.json();
  },

  async getEvaluation(jobId: string): Promise<EvaluationResponse> {
    const res = await fetch(`${API_BASE}/evaluate/${jobId}`);
    if (!res.ok) throw new Error('Failed to fetch evaluation');
    return res.json();
  },

  async calibrateWithGCPs(jobId: string, gcps: GCPItem[]): Promise<ReconstructionSummary> {
    const res = await fetch(`${API_BASE}/gcp/${jobId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gcps })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'GCP Calibration failed');
    }
    return res.json();
  },

  async getReport(jobId: string) {
    const res = await fetch(`${API_BASE}/results/${jobId}/report`);
    if (!res.ok) throw new Error('Failed to fetch project report');
    return res.json();
  },

  async inspectPoint(
    jobId: string,
    params: { pixel_x?: number; pixel_y?: number; x_pct?: number; y_pct?: number }
  ): Promise<PointInspectionResult> {
    const query = new URLSearchParams();
    if (params.pixel_x !== undefined) query.set('pixel_x', params.pixel_x.toString());
    if (params.pixel_y !== undefined) query.set('pixel_y', params.pixel_y.toString());
    if (params.x_pct !== undefined) query.set('x_pct', params.x_pct.toString());
    if (params.y_pct !== undefined) query.set('y_pct', params.y_pct.toString());

    const res = await fetch(`${API_BASE}/results/${jobId}/inspect-point?${query.toString()}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to inspect terrain point');
    }
    return res.json();
  },

  getExportUrl(jobId: string): string {
    return `${API_BASE}/results/${jobId}/export`;
  }
};
