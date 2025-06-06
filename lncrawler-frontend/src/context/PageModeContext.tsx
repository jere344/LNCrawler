import React, { createContext, useContext, useState, ReactNode } from 'react';

interface PageModeContextType {
  isPageModeActive: boolean;
  setPageModeActive: (active: boolean) => void;
}

const PageModeContext = createContext<PageModeContextType | undefined>(undefined);

export const usePageMode = () => {
  const context = useContext(PageModeContext);
  if (context === undefined) {
    throw new Error('usePageMode must be used within a PageModeProvider');
  }
  return context;
};

interface PageModeProviderProps {
  children: ReactNode;
}

export const PageModeProvider: React.FC<PageModeProviderProps> = ({ children }) => {
  const [isPageModeActive, setIsPageModeActive] = useState(false);

  const setPageModeActive = (active: boolean) => {
    setIsPageModeActive(active);
  };

  return (
    <PageModeContext.Provider value={{ isPageModeActive, setPageModeActive }}>
      {children}
    </PageModeContext.Provider>
  );
};
