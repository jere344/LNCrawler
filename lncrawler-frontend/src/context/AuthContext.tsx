import React, { createContext, useContext, useState, useEffect } from 'react';
import { authService } from '../services/api';

interface AuthContextType {
  isAuthenticated: boolean;
  user: any;
  login: (username: string, password: string) => Promise<any>;
  logout: () => Promise<void>;
  refreshUser: () => void;
  updateProfile: (profileData: any) => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false,
  user: null,
  login: async () => ({}),
  logout: async () => {},
  refreshUser: () => {},
  updateProfile: async () => {},
});

export const useAuth = () => useContext(AuthContext);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [user, setUser] = useState<any>(null);

  const checkAuthStatus = () => {
    const isLoggedIn = authService.isAuthenticated();
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
    window.addEventListener('storage', (event) => {
      if (event.key === 'authToken' || event.key === 'user') {
        checkAuthStatus();
      }
    });
    
    return () => {
      window.removeEventListener('storage', checkAuthStatus);
    };
  }, []);

  const login = async (username: string, password: string) => {
    const response = await authService._login({ username, password });
    checkAuthStatus();
    return response;
  };

  const logout = async () => {
    await authService._logout();
    setIsAuthenticated(false);
    setUser(null);
  };

  const refreshUser = async () => {
    if (isAuthenticated) {
      try {
        const userData = await authService.getProfile();
        setUser(userData);
        localStorage.setItem('user', JSON.stringify(userData));
      } catch (error) {
        console.error('Error refreshing user data:', error);
      }
    }
  };

  const updateProfile = async (profileData: any) => {
    try {
      const updatedUser = await authService._updateProfile(profileData);
      setUser(updatedUser);
      localStorage.setItem('user', JSON.stringify(updatedUser));
    }
    catch (error) {
      console.error('Error updating profile:', error);
    }
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, user, login, logout, refreshUser, updateProfile }}>
      {children}
    </AuthContext.Provider>
  );
};
