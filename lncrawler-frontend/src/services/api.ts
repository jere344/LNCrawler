import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8185';

// More robust function to get CSRF token from cookies
const getCsrfToken = (): string | null => {
  const cookieValue = document.cookie
    .split('; ')
    .find(row => row.startsWith('csrftoken='))
    ?.split('=')[1];
  return cookieValue || null;
};

// Function to explicitly fetch CSRF token when needed
const fetchCsrfToken = async (): Promise<string | null> => {
  try {
    // Make a GET request to an endpoint that will set the CSRF cookie
    await axios.get(`${API_BASE_URL}/csrf-token/`, { withCredentials: true });
    return getCsrfToken();
  } catch (error) {
    console.error('Error fetching CSRF token:', error);
    return null;
  }
};

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

api.interceptors.request.use(async (config) => {
  // Only add CSRF token for non-GET/HEAD/OPTIONS requests
  if (!['get', 'head', 'options'].includes(config.method?.toLowerCase() || '')) {
    let csrfToken = getCsrfToken();
    
    // If we don't have a token yet, try to fetch it
    if (!csrfToken) {
      csrfToken = await fetchCsrfToken();
    }
    
    if (csrfToken) {
      config.headers['X-CSRFToken'] = csrfToken;
    } else {
      console.warn('CSRF token not available');
    }
  }
  return config;
}, (error) => {
  return Promise.reject(error);
});

fetchCsrfToken().catch(err => console.error('Initial CSRF token fetch failed:', err));

// Export services from their dedicated files
export { searchService } from './search.service';
export { downloadService } from './download.service';
export { jobService } from './job.service';
export { novelService } from './novel.service';
export { commentService } from './comment.service';
export { authService } from './auth.service';
export { userService } from './user.service';
export { reviewService } from './review.service';
export { readingListService } from './readinglist.service';

// Add interceptor to set the auth token on startup
const token = localStorage.getItem('authToken');
if (token) {
  api.defaults.headers.common['Authorization'] = `Token ${token}`;
}

export default api;
