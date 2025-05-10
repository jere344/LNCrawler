import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// Search service functions
export const searchService = {
  startSearch: async (query: string) => {
    const response = await api.post('/downloader/search/start/', { query });
    return response.data;
  },
  
  getSearchStatus: async (jobId: string) => {
    const response = await api.get(`/downloader/search/status/${jobId}/`);
    
    // Calculate progress percentage if not already provided
    if (response.data.progress !== undefined && response.data.total_items !== undefined) {
      const total = response.data.total_items || 1;
      response.data.progress_percentage = Math.floor((response.data.progress / total) * 100);
    }
    
    return response.data;
  },
  
  getSearchResults: async (jobId: string) => {
    const response = await api.get(`/downloader/search/results/${jobId}/`);
    return response.data;
  },
};

export const downloadService = {
  startDownload: async (
    jobId: string, 
    params: { 
      novel_index: number; 
      source_index: number;
    }
  ) => {
    const response = await api.post(`/downloader/download/start/${jobId}/`, params);
    return response.data;
  },
  
  getDownloadStatus: async (jobId: string) => {
    const response = await api.get(`/downloader/download/status/${jobId}/`);
    return response.data;
  },
  
  getDownloadResults: async (jobId: string) => {
    const response = await api.get(`/downloader/download/results/${jobId}/`);
    return response.data;
  },
};

export const jobService = {
  cancelJob: async (jobId: string) => {
    const response = await api.post(`/downloader/jobs/cancel/${jobId}/`);
    return response.data;
  },
  
  listJobs: async () => {
    const response = await api.get('/downloader/jobs/');
    return response.data;
  },
  
  getJobDetails: async (jobId: string) => {
    const response = await api.get(`/downloader/jobs/${jobId}/`);
    return response.data;
  },
};

export default api;
