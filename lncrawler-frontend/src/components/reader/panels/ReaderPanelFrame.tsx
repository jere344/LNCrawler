import { useEffect, useRef, type ReactNode } from 'react';
import { Box, IconButton, Paper, Typography, type SxProps, type Theme } from '@mui/material';
import { useTranslation } from 'react-i18next';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import type { ReaderLayoutMode } from '../hooks/useReaderLayout';
import { useReturnFocus } from '../hooks/useReturnFocus';
import DirectionalIcon from '../DirectionalIcon';
import { panelWidth } from './panelLayout';

// Where the panel sits: full screen on phones, a side panel with the text still visible on wider layouts
const placement = (mode: ReaderLayoutMode): SxProps<Theme> => {
  const width = panelWidth(mode);
  if (width === null) return { inset: 0 };
  return { top: 0, bottom: 0, insetInlineEnd: 0, width, maxWidth: '100%' };
};

interface ReaderPanelFrameProps {
  title: string;
  mode: ReaderLayoutMode;
  onBack: () => void;
  // Whether the header shows the back button (false on desktop, where the panel has a close button instead)
  showBack?: boolean;
  // Extra controls at the end of the header
  headerExtra?: ReactNode;
  children: ReactNode;
}

// Generic panel shell: a header with a back button, and a scrollable body. Not modal.
const ReaderPanelFrame = ({ title, mode, onBack, showBack = true, headerExtra, children }: ReaderPanelFrameProps) => {
  const { t } = useTranslation();
  const backRef = useRef<HTMLButtonElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  // Focus lands on the back button, or on the frame itself when there is none (desktop)
  useReturnFocus(showBack ? backRef : frameRef);

  // Full-screen panels: the page behind must not scroll, even when focus is on the back button
  useEffect(() => {
    if (mode !== 'phone') return;
    const previous = document.documentElement.style.overflow;
    document.documentElement.style.overflow = 'hidden';
    return () => {
      document.documentElement.style.overflow = previous;
    };
  }, [mode]);

  return (
    <Paper
      ref={frameRef}
      tabIndex={-1}
      role="dialog"
      data-reader-panel
      aria-label={title}
      square
      elevation={8}
      sx={{
        position: 'fixed',
        zIndex: (theme) => theme.zIndex.appBar + 3,
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
        outline: 'none',
        ...placement(mode),
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 1, py: 1, borderBottom: 1, borderColor: 'divider' }}>
        {showBack && (
          <IconButton ref={backRef} onClick={onBack} aria-label={t('readerDisplay.back')}>
            <DirectionalIcon><ArrowBackIcon /></DirectionalIcon>
          </IconButton>
        )}
        <Typography variant="h6" component="h2" noWrap sx={{ flex: 1, minWidth: 0, fontSize: '1.1rem' }}>
          {title}
        </Typography>
        {headerExtra}
      </Box>

      <Box sx={{ flex: 1, minHeight: 0, overflowY: 'auto', p: 2 }}>{children}</Box>
    </Paper>
  );
};

export default ReaderPanelFrame;
