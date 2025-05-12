import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// Function to get CSRF token from cookies
const getCsrfToken = (): string | null => {
  const cookieValue = document.cookie
    .split('; ')
    .find(row => row.startsWith('csrftoken='))
    ?.split('=')[1];
  return cookieValue || null;
};

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// Add request interceptor to include CSRF token for mutating requests
api.interceptors.request.use(config => {
  // Only add CSRF token for non-GET requests
  if (config.method !== 'get') {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      config.headers['X-CSRFToken'] = csrfToken;
    }
  }
  return config;
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

// Novel service functions updated for the new URL structure
export const novelService = {
  listNovels: async (page = 1, pageSize = 24) => {
    const response = await api.get(`/novels/?page=${page}&page_size=${pageSize}`);
    return response.data;
  },
  
  // Get novel details by slug
  getNovelDetail: async (novelSlug: string) => {
    const response = await api.get(`/novels/${novelSlug}/`);
    return response.data;
  },
  
  // Get source details by slug
  getSourceDetail: async (novelSlug: string, sourceSlug: string) => {
    const response = await api.get(`/novels/${novelSlug}/${sourceSlug}/`);
    return response.data;
  },
  
  // Get chapters by novel and source slugs
  getNovelChapters: async (novelSlug: string, sourceSlug: string) => {
    const response = await api.get(`/novels/${novelSlug}/${sourceSlug}/chapters/`);
    return response.data;
  },
  
  // Get chapter content by number
  getChapterContent: async (novelSlug: string, sourceSlug: string, chapterNumber: number) => {
    const response = await api.get(`/novels/${novelSlug}/${sourceSlug}/chapter/${chapterNumber}/`);
    return response.data;
  },

  voteSource : async (novelSlug: string, sourceSlug: string, voteType: 'up' | 'down') => {
    const response = await api.post(
      `/novels/${novelSlug}/${sourceSlug}/vote/`, 
      { vote_type: voteType }
    );
    return response.data;
  },

  // Rate a novel (1-5 stars)
  rateNovel: async (novelSlug: string, rating: number) => {
    const response = await api.post(`/novels/${novelSlug}/rate/`, { rating });
    return response.data;
  },
};

export default api;
