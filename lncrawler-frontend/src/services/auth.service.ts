import api from './api';

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
    try {
      // Revoke the token server-side before dropping it locally.
      const response = await api.post('/auth/logout/');
      return response.data;
    } finally {
      // Clear auth data from storage regardless of the server response.
      localStorage.removeItem('authToken');
      localStorage.removeItem('user');
      delete api.defaults.headers.common['Authorization'];
    }
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
    banner?: File;
    bio?: string;
    social_links?: Record<string, string>;
    privacy_settings?: Record<string, string>;
    preferred_ui_language?: string;
    preferred_languages?: string[];
    language_filter_enabled?: boolean;
    discoverable?: boolean;
    show_r18?: 'yes' | 'no' | 'blur';
  }) => {
    // Use FormData if there's an image upload (profile_pic or banner)
    if (profileData.profile_pic || profileData.banner) {
      const formData = new FormData();
      
      Object.entries(profileData).forEach(([key, value]) => {
        if (value === undefined) return;
        if (value instanceof File) {
          formData.append(key, value);
        } else if (typeof value === 'object' && value !== null) {
          formData.append(key, JSON.stringify(value));
        } else {
          formData.append(key, String(value));
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
  
  // Change password
  changePassword: async (passwordData: {
    old_password: string;
    new_password: string;
    new_password2: string;
  }) => {
    const response = await api.post('/auth/change-password/', passwordData);
    
    // Update token if returned
    if (response.data.token) {
      localStorage.setItem('authToken', response.data.token);
      api.defaults.headers.common['Authorization'] = `Token ${response.data.token}`;
    }
    
    return response.data;
  },

  // Forgot password
  forgotPassword: async (email: string) => {
    const response = await api.post('/auth/forgot-password/', { email });
    return response.data;
  },

  // Reset password
  resetPassword: async (resetData: {
    token: string;
    new_password: string;
    new_password2: string;
  }) => {
    const response = await api.post('/auth/reset-password/', resetData);
    return response.data;
  },

  // Helper method to check if user is authenticated
  isAuthenticated: () => {
    return !!localStorage.getItem('authToken');
  },
  
  // Keep the shared API auth header in sync with localStorage. Needed for
  // cross-tab login/logout, where the storage event fires but this module's
  // in-memory `defaults` is stale.
  syncAuthHeader: () => {
    const token = localStorage.getItem('authToken');
    if (token) {
      api.defaults.headers.common['Authorization'] = `Token ${token}`;
    } else {
      delete api.defaults.headers.common['Authorization'];
    }
  },
  
  // Helper method to get current user
  getCurrentUser: () => {
    const userStr = localStorage.getItem('user');
    if (!userStr) return null;
    try {
      return JSON.parse(userStr);
    } catch {
      // A corrupted entry must not crash the app; drop it.
      localStorage.removeItem('user');
      return null;
    }
  },
};
