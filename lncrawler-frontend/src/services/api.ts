const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8185';

interface RequestConfig {
  headers?: Record<string, string>;
  params?: Record<string, string | number | boolean | undefined>;
}

export interface ApiResponse {
  // Matches axios's untyped `response.data` contract used across the services.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any;
  status: number;
  statusText: string;
  headers: Headers;
}

export interface ApiError extends Error {
  response?: ApiResponse;
}

// Kept as a mutable object so callers can set/clear the auth header,
// mirroring the old axios `api.defaults.headers.common` API.
const defaults = { headers: { common: {} as Record<string, string> } };

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
    await fetch(`${API_BASE_URL}/csrf-token/`, { credentials: 'include' });
    return getCsrfToken();
  } catch (error) {
    console.error('Error fetching CSRF token:', error);
    return null;
  }
};

const request = async (
  method: string,
  url: string,
  body?: unknown,
  config?: RequestConfig,
): Promise<ApiResponse> => {
  const isFormData = body instanceof FormData;

  const headers: Record<string, string> = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...defaults.headers.common,
    ...config?.headers,
  };

  // Only add CSRF token for non-GET/HEAD/OPTIONS requests
  if (!['get', 'head', 'options'].includes(method)) {
    let csrfToken = getCsrfToken();
    if (!csrfToken) {
      csrfToken = await fetchCsrfToken();
    }
    if (csrfToken) {
      headers['X-CSRFToken'] = csrfToken;
    } else {
      console.warn('CSRF token not available');
    }
  }

  // Never set Content-Type for FormData: the browser must add the boundary.
  if (isFormData) delete headers['Content-Type'];

  let fullUrl = `${API_BASE_URL}${url}`;
  if (config?.params) {
    const query = new URLSearchParams();
    Object.entries(config.params).forEach(([key, value]) => {
      if (value !== undefined) query.append(key, String(value));
    });
    const qs = query.toString();
    if (qs) fullUrl += (url.includes('?') ? '&' : '?') + qs;
  }

  const response = await fetch(fullUrl, {
    method: method.toUpperCase(),
    headers,
    credentials: 'include',
    body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
  });

  const text = await response.text();
  const contentType = response.headers.get('content-type') || '';
  let data: unknown = text;
  if (contentType.includes('application/json')) {
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      // leave raw text in place of malformed JSON
    }
  } else if (text === '') {
    data = null;
  }

  if (!response.ok) {
    const error = new Error(`Request failed with status code ${response.status}`) as Error & {
      response: ApiResponse;
    };
    error.response = { data, status: response.status, statusText: response.statusText, headers: response.headers };
    throw error;
  }

  return { data, status: response.status, statusText: response.statusText, headers: response.headers };
};

const api = {
  defaults,
  get: (url: string, config?: RequestConfig) => request('get', url, undefined, config),
  post: (url: string, body?: unknown, config?: RequestConfig) => request('post', url, body, config),
  put: (url: string, body?: unknown, config?: RequestConfig) => request('put', url, body, config),
  patch: (url: string, body?: unknown, config?: RequestConfig) => request('patch', url, body, config),
  delete: (url: string, config?: RequestConfig) => request('delete', url, undefined, config),
};

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

// Set the auth token on startup
const token = localStorage.getItem('authToken');
if (token) {
  defaults.headers.common['Authorization'] = `Token ${token}`;
}

export default api;
