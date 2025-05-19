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

// Export services from their dedicated files
export { searchService } from './search.service';
export { downloadService } from './download.service';
export { jobService } from './job.service';
export { novelService } from './novel.service';
export { commentService } from './comment.service';
export { authService } from './auth.service';
export { userService } from './user.service';

// Add interceptor to set the auth token on startup
const token = localStorage.getItem('authToken');
if (token) {
  api.defaults.headers.common['Authorization'] = `Token ${token}`;
}

export default api;
