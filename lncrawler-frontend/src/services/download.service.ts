import api from './api';

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
  
  // New method for direct URL downloads
  startDirectDownload: async (novelUrl: string) => {
    const response = await api.post('/downloader/download/start-direct/', { novel_url: novelUrl });
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
