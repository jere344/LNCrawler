import api from './api';

export const jobService = {
  cancelJob: async (jobId: string) => {
    const response = await api.post(`/downloader/jobs/cancel/${jobId}/`);
    return response.data;
  },
  
  listJobs: async (activeOnly = false, jobType?: string) => {
    const params = {
      ...(activeOnly ? { active: 1 } : {}),
      ...(jobType ? { job_type: jobType } : {}),
    };
    const response = await api.get('/downloader/jobs/', { params });
    return response.data;
  },
  
  getJobDetails: async (jobId: string) => {
    const response = await api.get(`/downloader/jobs/${jobId}/`);
    return response.data;
  },
};
