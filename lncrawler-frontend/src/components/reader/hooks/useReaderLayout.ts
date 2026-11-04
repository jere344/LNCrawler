import { useMediaQuery, useTheme } from '@mui/material';

export type ReaderLayoutMode = 'phone' | 'phoneLandscape' | 'tablet' | 'desktop';

// Touch layouts show the bars on tap; the desktop layout keeps a toolbar. Features are the same on every layout.
export function useReaderLayout() {
  const theme = useTheme();
  const isNarrow = useMediaQuery(theme.breakpoints.down('sm'));
  const isWide = useMediaQuery(theme.breakpoints.up('lg'));
  const isPhoneLandscape = useMediaQuery('(orientation: landscape) and (max-height: 500px)');

  let mode: ReaderLayoutMode = 'desktop';
  if (isPhoneLandscape) mode = 'phoneLandscape';
  else if (isNarrow) mode = 'phone';
  else if (!isWide) mode = 'tablet';

  return { mode, isDesktop: mode === 'desktop', isNarrow };
}
