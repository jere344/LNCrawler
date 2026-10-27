import React, { createContext, useContext, useState, useEffect } from 'react';
import { authService } from '../services/api';
import { User } from '../models/user_types';
import { AUTH_TOKEN_KEY, AUTH_USER_KEY } from '../utils/storage';
import { clearHistoryCache } from '../router/loaders';
import { clearSourceDetailCache } from '../components/novels/sourceDetail/useSourceDetail';

interface AuthContextType {
  isAuthenticated: boolean;
  user: User | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => void;
  updateProfile: (profileData: Parameters<typeof authService._updateProfile>[0]) => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false,
  user: null,
  login: async () => {},
  logout: async () => {},
  refreshUser: () => {},
  updateProfile: async () => {},
});

export const useAuth = () => useContext(AuthContext);

// Pages kept for back/forward carry the account's bookmarks, ratings and
// recommendations, so they are dropped whenever the account changes.
const forgetAccountPages = () => {
  clearHistoryCache();
  clearSourceDetailCache();
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [user, setUser] = useState<User | null>(null);

  const checkAuthStatus = () => {
    const isLoggedIn = authService.isAuthenticated();
    // Keep the API auth header in sync (covers cross-tab login/logout).
    authService.syncAuthHeader();
    setIsAuthenticated(isLoggedIn);
    
    if (isLoggedIn) {
      setUser(authService.getCurrentUser());
    } else {
      setUser(null);
    }
  };

  useEffect(() => {
    checkAuthStatus();
    
    // Listen for storage events (for when user logs in/out in another tab)
    const handleStorage = (event: StorageEvent) => {
      if (event.key === AUTH_TOKEN_KEY || event.key === AUTH_USER_KEY) {
        forgetAccountPages();
        checkAuthStatus();
      }
    };
    window.addEventListener('storage', handleStorage);
    
    return () => {
      window.removeEventListener('storage', handleStorage);
    };
  }, []);

  const login = async (username: string, password: string) => {
    const response = await authService._login({ username, password });
    forgetAccountPages();
    checkAuthStatus();
    return response;
  };

  const logout = async () => {
    forgetAccountPages();
    setIsAuthenticated(false);
    setUser(null);
    await authService._logout();
  };

  const refreshUser = async () => {
    if (isAuthenticated) {
      try {
        const userData = await authService.getProfile();
        setUser(userData);
        localStorage.setItem(AUTH_USER_KEY, JSON.stringify(userData));
      } catch (error) {
        console.error('Error refreshing user data:', error);
      }
    }
  };

  const updateProfile = async (profileData: Parameters<typeof authService._updateProfile>[0]) => {
    try {
      const updatedUser = await authService._updateProfile(profileData);
      setUser(updatedUser);
      localStorage.setItem(AUTH_USER_KEY, JSON.stringify(updatedUser));
    }
    catch (error) {
      console.error('Error updating profile:', error);
      throw error;
    }
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, user, login, logout, refreshUser, updateProfile }}>
      {children}
    </AuthContext.Provider>
  );
};
