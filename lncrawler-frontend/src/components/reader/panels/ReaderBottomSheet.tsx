import { type KeyboardEvent, type ReactNode, type RefObject } from 'react';
import { Box, Paper } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useReturnFocus } from '../hooks/useReturnFocus';
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion';
import { useEnteredOnFrame } from '../hooks/useEnteredOnFrame';
import { useDocumentScrollLock } from '../hooks/useDocumentScrollLock';
import { useKeyboardAvoidance } from '../hooks/useKeyboardAvoidance';
import { sheetDragResult, usePointerDragY } from '../hooks/sheetDrag';

const HANDLE_HEIGHT = 22;
const PARTIAL_HEIGHT = '62dvh';
// Full height leaves a strip of the text above the sheet, so the reader is still there
const FULL_GAP = 24;

interface ReaderBottomSheetProps {
  title: string;
  // Whether the sheet is at full height by the user's choice
  full: boolean;
  onFullChange: (full: boolean) => void;
  onClose: () => void;
  // A composer is open in the sheet: the sheet is shown at full height, and a drag down closes the composer
  composing?: boolean;
  onStopComposing?: () => void;
  // Takes focus when the sheet opens
  focusRef: RefObject<HTMLElement | null>;
  // Space kept under the sheet, for the TTS bar
  bottomOffset?: number;
  children: ReactNode;
}

// Phone panel that slides up from the bottom and can be dragged to full height. Modal in effect: the page behind is locked.
const ReaderBottomSheet = ({ title, full, onFullChange, onClose, composing = false, onStopComposing, focusRef, bottomOffset = 0, children }: ReaderBottomSheetProps) => {
  const { t } = useTranslation();
  const reducedMotion = usePrefersReducedMotion();
  const entered = useEnteredOnFrame();
  const tall = full || composing;

  useDocumentScrollLock(true);
  // With the keyboard up the sheet keeps its top where it was and its bottom sits on the keyboard
  const keyboard = useKeyboardAvoidance(composing);
  useReturnFocus(focusRef);

  // A drag up opens the sheet fully; a drag down closes the composer, shrinks the sheet, or closes it when it is already partial. A tap toggles it.
  const drag = usePointerDragY((dy) => {
    const result = sheetDragResult(dy, full, composing);
    if (result === 'expand') onFullChange(true);
    else if (result === 'shrink') onFullChange(false);
    else if (result === 'close') onClose();
    else if (result === 'stopComposing') onStopComposing?.();
    else if (result === 'toggle') onFullChange(!tall);
  });

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onFullChange(!tall);
  };

  return (
    <Paper
      role="dialog"
      aria-modal="true"
      data-reader-panel
      aria-label={title}
      tabIndex={-1}
      elevation={8}
      sx={{
        position: 'fixed',
        zIndex: (theme) => theme.zIndex.appBar + 3,
        insetInline: 0,
        // Sits above the TTS bar
        bottom: keyboard ? 'auto' : bottomOffset,
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
        outline: 'none',
        // The full height stops short of the top strip and of the bar below
        height: keyboard ? keyboard.height - FULL_GAP : tall ? `calc(100dvh - ${FULL_GAP + bottomOffset}px)` : PARTIAL_HEIGHT,
        ...(keyboard ? { top: keyboard.top + FULL_GAP } : {}),
        borderStartStartRadius: '16px',
        borderStartEndRadius: '16px',
        transition: reducedMotion ? 'none' : keyboard ? 'transform 0.25s ease-out' : 'transform 0.25s ease-out, height 0.25s ease-out',
        // Starts below the screen until the first frame, then slides up
        ...(!entered && !reducedMotion ? { transform: 'translateY(100%)' } : {}),
      }}
    >
      <Box
        role="button"
        tabIndex={0}
        aria-label={t('readerComments.resize')}
        aria-expanded={tall}
        onPointerDown={drag.onPointerDown}
        onPointerUp={drag.onPointerUp}
        onPointerCancel={drag.onPointerCancel}
        onKeyDown={handleKeyDown}
        sx={{
          flex: 'none',
          height: HANDLE_HEIGHT,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          touchAction: 'none',
          '&:focus-visible': { outline: (theme) => `2px solid ${theme.palette.primary.main}`, outlineOffset: -2 },
        }}
      >
        <Box sx={{ width: 36, height: 4, borderRadius: '2px', bgcolor: 'text.secondary', opacity: 0.5 }} />
      </Box>

      <Box sx={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {children}
      </Box>
    </Paper>
  );
};

export default ReaderBottomSheet;
