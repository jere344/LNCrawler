import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8185';

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
  
  // Get chapters by novel and source slugs with pagination
  getNovelChapters: async (novelSlug: string, sourceSlug: string, page = 1, pageSize = 100) => {
    const response = await api.get(`/novels/${novelSlug}/${sourceSlug}/chapters/`, {
      params: { page, page_size: pageSize }
    });
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

  // Get comments for a novel
  getNovelComments: async (novelSlug: string) => {
    const response = await api.get(`/novels/${novelSlug}/comments/`);
    return response.data;
  },
  
  // Add a comment to a novel
  addNovelComment: async (novelSlug: string, commentData: { 
    author_name: string; 
    message: string; 
    contains_spoiler: boolean;
    parent_id?: string; // Optional parent ID for replies
  }) => {
    const response = await api.post(
      `/novels/${novelSlug}/comments/add/`,
      commentData
    );
    return response.data;
  },
  
  // Get comments for a chapter
  getChapterComments: async (novelSlug: string, sourceSlug: string, chapterNumber: number) => {
    const response = await api.get(
      `/novels/${novelSlug}/${sourceSlug}/chapter/${chapterNumber}/comments/`
    );
    return response.data;
  },
  
  // Add a comment to a chapter
  addChapterComment: async (
    novelSlug: string,
    sourceSlug: string,
    chapterNumber: number,
    commentData: { 
      author_name: string; 
      message: string; 
      contains_spoiler: boolean;
      parent_id?: string; // Optional parent ID for replies
    }
  ) => {
    const response = await api.post(
      `/novels/${novelSlug}/${sourceSlug}/chapter/${chapterNumber}/comments/add/`,
      commentData
    );
    return response.data;
  },

  searchNovels: async (params: {
    query?: string;
    page?: number;
    page_size?: number;
    genre?: string[];
    tag?: string[];
    author?: string[];
    status?: string;
    language?: string;
    min_rating?: number;
    sort_by?: 'title' | 'rating' | 'date_added' | 'popularity' | 'trending' | 'last_updated';
    sort_order?: 'asc' | 'desc';
  }) => {
    // Build query string
    const queryParams = new URLSearchParams();
    
    if (params.query) queryParams.append('query', params.query);
    if (params.page) queryParams.append('page', params.page.toString());
    if (params.page_size) queryParams.append('page_size', params.page_size.toString());
    if (params.status) queryParams.append('status', params.status);
    if (params.language) queryParams.append('language', params.language);
    if (params.min_rating) queryParams.append('min_rating', params.min_rating.toString());
    if (params.sort_by) queryParams.append('sort_by', params.sort_by);
    if (params.sort_order) queryParams.append('sort_order', params.sort_order);
    
    // Handle array parameters
    if (params.genre && params.genre.length) {
      params.genre.forEach(genre => queryParams.append('genre', genre));
    }
    
    if (params.tag && params.tag.length) {
      params.tag.forEach(tag => queryParams.append('tag', tag));
    }
    
    if (params.author && params.author.length) {
      params.author.forEach(author => queryParams.append('author', author));
    }
    
    const response = await api.get(`/novels/search/?${queryParams}`);
    return response.data;
  },

  // Add this function to your novelService object
  getAutocompleteSuggestions: async (type: 'genre' | 'tag' | 'author', query: string): Promise<{ name: string; count: number }[]> => {
    const response = await api.get(`/novels/autocomplete/`, {
      params: {
        type,
        query,
        limit: 10
      }
    });
    return response.data;
  },

  // Get a random featured novel
  getRandomFeaturedNovel: async () => {
    const response = await api.get('/novels/featured/random/');
    return response.data;
  },
};

export const commentService = {
  voteComment: async (commentId: string, voteType: 'up' | 'down') => {
    const response = await api.post(`/comments/${commentId}/vote/`, { vote_type: voteType });
    return response.data; // Expects { id, upvotes, downvotes, vote_score }
  },
};

// Authentication service functions
export const authService = {
  // Register a new user
  register: async (userData: {
    username: string;
    email: string;
    password: string;
    password2: string;
    profile_pic?: File;
  }) => {
    // Use FormData if there's a profile image upload
    let formData;
    if (userData.profile_pic) {
      formData = new FormData();
      formData.append('username', userData.username);
      formData.append('email', userData.email);
      formData.append('password', userData.password);
      formData.append('password2', userData.password2);
      formData.append('profile_pic', userData.profile_pic);
      
      const response = await api.post('/auth/register/', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return response.data;
    } else {
      const response = await api.post('/auth/register/', userData);
      return response.data;
    }
  },
  
  // Login user
  _login: async (credentials: { username: string; password: string }) => {
    const response = await api.post('/auth/login/', credentials);
    
    // Store the token in localStorage
    if (response.data.token) {
      localStorage.setItem('authToken', response.data.token);
      localStorage.setItem('user', JSON.stringify(response.data.user));
      
      // Set token in axios defaults for future requests
      api.defaults.headers.common['Authorization'] = `Token ${response.data.token}`;
    }
    
    return response.data;
  },
  
  // Logout user
  _logout: async () => {
    const response = await api.post('/auth/logout/');
    
    // Clear auth data from storage
    localStorage.removeItem('authToken');
    localStorage.removeItem('user');
    
    // Remove authorization header
    delete api.defaults.headers.common['Authorization'];
    
    return response.data;
  },
  
  // Get current user profile
  getProfile: async () => {
    const response = await api.get('/auth/profile/');
    return response.data;
  },
  
  // Update user profile
  _updateProfile: async (profileData: {
    username?: string;
    email?: string;
    profile_pic?: File;
  }) => {
    // Use FormData if there's a profile image upload
    if (profileData.profile_pic) {
      const formData = new FormData();
      
      Object.entries(profileData).forEach(([key, value]) => {
        if (value !== undefined) {
          formData.append(key, value);
        }
      });
      
      const response = await api.patch('/auth/profile/', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      
      // Update stored user info
      if (response.data) {
        localStorage.setItem('user', JSON.stringify(response.data));
      }
      
      return response.data;
    } else {
      const response = await api.patch('/auth/profile/', profileData);
      
      // Update stored user info
      if (response.data) {
        localStorage.setItem('user', JSON.stringify(response.data));
      }
      
      return response.data;
    }
  },
  
  // Check if a username or email already exists
  checkUserExists: async (field: { username?: string; email?: string }) => {
    const params = new URLSearchParams();
    if (field.username) params.append('username', field.username);
    if (field.email) params.append('email', field.email);
    
    const response = await api.get(`/auth/user-exists/?${params}`);
    return response.data;
  },
  
  // Helper method to check if user is authenticated
  isAuthenticated: () => {
    return !!localStorage.getItem('authToken');
  },
  
  // Helper method to get current user
  getCurrentUser: () => {
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
  },
};

// Add interceptor to set the auth token on startup
const token = localStorage.getItem('authToken');
if (token) {
  api.defaults.headers.common['Authorization'] = `Token ${token}`;
}

export default api;
