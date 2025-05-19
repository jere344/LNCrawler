import api from './api';

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
