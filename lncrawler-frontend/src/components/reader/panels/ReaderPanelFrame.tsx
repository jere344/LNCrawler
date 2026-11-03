import { useEffect, useRef, type CSSProperties, type ReactNode, type Ref } from 'react';
import { Box, IconButton, Paper, Typography, useForkRef, type SxProps, type Theme } from '@mui/material';
import { useTranslation } from 'react-i18next';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import type { ReaderLayoutMode } from '../hooks/useReaderLayout';
import { useReturnFocus } from '../hooks/useReturnFocus';
import DirectionalIcon from '../DirectionalIcon';
import { CHAPTER_LIST_WIDTH, panelWidth } from './panelLayout';

// Where the panel sits. End side: full screen on phones, a side panel with the text still visible on wider layouts.
// Start side (the chapter list): an overlay on the left of phones, a side panel beside the text elsewhere.
const placement = (mode: ReaderLayoutMode, side: 'start' | 'end'): SxProps<Theme> => {
  if (side === 'start') {
    if (mode === 'phone') return { top: 0, bottom: 0, insetInlineStart: 0, width: 'min(88%, 340px)', maxWidth: '100%' };
    return { top: 0, bottom: 0, insetInlineStart: 0, width: CHAPTER_LIST_WIDTH, maxWidth: '100%' };
  }
  const width = panelWidth(mode);
  if (width === null) return { inset: 0 };
  return { top: 0, bottom: 0, insetInlineEnd: 0, width, maxWidth: '100%' };
};

interface ReaderPanelFrameProps {
  title: string;
  mode: ReaderLayoutMode;
  // The edge the panel sits on
  side?: 'start' | 'end';
  onBack: () => void;
  // Whether the header shows the back button (false on desktop, where the panel has a close button instead)
  showBack?: boolean;
  // Extra controls at the end of the header
  headerExtra?: ReactNode;
  // No padding on the body, which then scrolls nothing itself: the content lays out and scrolls its own parts
  flush?: boolean;
  // The transition that opens the panel reaches the frame through these
  ref?: Ref<HTMLDivElement>;
  style?: CSSProperties;
  children: ReactNode;
}

// Generic panel shell: a header with a back button, and a scrollable body. Not modal.
const ReaderPanelFrame = ({
  title,
  mode,
  side = 'end',
  onBack,
  showBack = true,
  headerExtra,
  flush = false,
  ref,
  style,
  children,
}: ReaderPanelFrameProps) => {
  const { t } = useTranslation();
  const backRef = useRef<HTMLButtonElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const mergedRef = useForkRef(frameRef, ref);
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
      ref={mergedRef}
      style={style}
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
        ...placement(mode, side),
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

      <Box sx={flush
        ? { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }
        : { flex: 1, minHeight: 0, overflowY: 'auto', p: 2 }}
      >
        {children}
      </Box>
    </Paper>
  );
};

export default ReaderPanelFrame;
