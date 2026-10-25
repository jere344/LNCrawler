import api from './api';
import { DownloadParams, DownloadStartResponse, DownloadStatus } from '@models/downloader_types';

export const downloadService = {
  startDownload: async (
    jobId: string,
    params: DownloadParams
  ) => {
    const response = await api.post(`/downloader/download/start/${jobId}/`, params);
    return response.data as DownloadStartResponse;
  },
  
  // New method for direct URL downloads
  startDirectDownload: async (novelUrl: string) => {
    const response = await api.post('/downloader/download/start-direct/', { novel_url: novelUrl });
    return response.data;
  },
  
  getDownloadStatus: async (jobId: string) => {
    const response = await api.get(`/downloader/download/status/${jobId}/`);
    return response.data as DownloadStatus;
  },
  
  getDownloadResults: async (jobId: string) => {
    const response = await api.get(`/downloader/download/results/${jobId}/`);
    return response.data;
  },
};
