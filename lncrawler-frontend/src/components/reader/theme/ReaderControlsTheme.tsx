import { useMemo, type ReactNode } from 'react';
import { ThemeProvider, useTheme } from '@mui/material/styles';
import { buildReaderControlsTheme } from './readerControlsTheme';
import { SiteThemeContext } from './siteTheme';

interface ReaderControlsThemeProps {
  backgroundColor: string | null;
  children: ReactNode;
}

// Restyles the controls it wraps (bars, display sheet, panels) to match the reader background
const ReaderControlsTheme = ({ backgroundColor, children }: ReaderControlsThemeProps) => {
  const siteTheme = useTheme();
  const theme = useMemo(() => buildReaderControlsTheme(siteTheme, backgroundColor), [siteTheme, backgroundColor]);

  return (
    <SiteThemeContext.Provider value={siteTheme}>
      <ThemeProvider theme={theme}>{children}</ThemeProvider>
    </SiteThemeContext.Provider>
  );
};

export default ReaderControlsTheme;
