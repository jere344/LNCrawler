import api from './api';

export const jobService = {
  cancelJob: async (jobId: string) => {
    const response = await api.post(`/downloader/jobs/cancel/${jobId}/`);
    return response.data;
  },
  
  listJobs: async (activeOnly = false) => {
    const response = await api.get('/downloader/jobs/', activeOnly ? { params: { active: 1 } } : undefined);
    return response.data;
  },
  
  getJobDetails: async (jobId: string) => {
    const response = await api.get(`/downloader/jobs/${jobId}/`);
    return response.data;
  },
};
