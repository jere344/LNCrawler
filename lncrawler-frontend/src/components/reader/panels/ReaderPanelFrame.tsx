import { useRef, type CSSProperties, type ReactNode, type Ref } from 'react';
import { Box, Paper, useForkRef, type SxProps, type Theme } from '@mui/material';
import type { ReaderLayoutMode } from '../hooks/useReaderLayout';
import { useReturnFocus } from '../hooks/useReturnFocus';
import { useDocumentScrollLock } from '../hooks/useDocumentScrollLock';
import { CHAPTER_LIST_WIDTH, panelWidth } from './panelLayout';
import ReaderPanelHeader from './ReaderPanelHeader';

// Where the panel sits. End side: full screen on phones, a side panel with the text still visible on wider layouts.
// Start side (the chapter list): an overlay on the left of phones, a side panel beside the text elsewhere.
// The end side takes `width` over the default panel width off phones.
const placement = (mode: ReaderLayoutMode, side: 'start' | 'end', width?: number): SxProps<Theme> => {
  if (side === 'start') {
    if (mode === 'phone') return { top: 0, bottom: 0, insetInlineStart: 0, width: 'min(88%, 340px)', maxWidth: '100%' };
    return { top: 0, bottom: 0, insetInlineStart: 0, width: CHAPTER_LIST_WIDTH, maxWidth: '100%' };
  }
  const endWidth = mode === 'phone' ? null : (width ?? panelWidth(mode));
  if (endWidth === null) return { inset: 0 };
  return { top: 0, bottom: 0, insetInlineEnd: 0, width: endWidth, maxWidth: '100%' };
};

interface ReaderPanelFrameProps {
  title: string;
  mode: ReaderLayoutMode;
  // The edge the panel sits on
  side?: 'start' | 'end';
  // Width of an end-side panel off phones, in place of the default panel width
  width?: number;
  // Goes back a level; needed when the back button shows
  onBack?: () => void;
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
  width,
  onBack,
  showBack = true,
  headerExtra,
  flush = false,
  ref,
  style,
  children,
}: ReaderPanelFrameProps) => {
  const backRef = useRef<HTMLButtonElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const mergedRef = useForkRef(frameRef, ref);
  // The back button shows when asked for and given; focus lands on it, or on the frame itself when there is none
  const back = showBack ? onBack : undefined;
  useReturnFocus(back ? backRef : frameRef);
  // Full-screen panels: the page behind must not scroll, even when focus is on the back button
  useDocumentScrollLock(mode === 'phone');

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
        ...placement(mode, side, width),
      }}
    >
      <ReaderPanelHeader
        title={title}
        onBack={back}
        backRef={backRef}
        extra={headerExtra}
        sx={{ px: 1, py: 1, borderBottom: 1, borderColor: 'divider' }}
      />

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
