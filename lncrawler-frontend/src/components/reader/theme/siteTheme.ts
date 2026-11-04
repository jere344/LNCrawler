import { createContext, useContext } from 'react';
import { useTheme, type Theme } from '@mui/material/styles';

// The site theme, kept for parts that must stay on it inside ReaderControlsTheme
export const SiteThemeContext = createContext<Theme | null>(null);

// The site theme even inside ReaderControlsTheme; the current theme when nothing provides it
export function useSiteTheme(): Theme {
  const current = useTheme();
  return useContext(SiteThemeContext) ?? current;
}
