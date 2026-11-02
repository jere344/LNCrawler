import { useEffect, useRef, useState, type PointerEvent } from 'react';
import { Box, Button, IconButton, Paper, Typography, type SxProps, type Theme } from '@mui/material';
import { useTranslation } from 'react-i18next';
import CloseIcon from '@mui/icons-material/Close';
import EditIcon from '@mui/icons-material/Edit';
import { useReaderSettings } from '../hooks/useReaderSettings';
import type { ReaderLayoutMode } from '../hooks/useReaderLayout';
import { useReturnFocus } from '../hooks/useReturnFocus';
import { READER_BOTTOM_BAR_HEIGHT } from '../controls/readerBarTypes';
import DisplayModuleGrid from './DisplayModuleGrid';

// A drag of the header this far down closes the sheet on touch layouts
const DRAG_CLOSE_DISTANCE = 40;

// Where the sheet sits on each layout (logical properties, so it mirrors under RTL)
const placement = (mode: ReaderLayoutMode, bottomOffset: number): SxProps<Theme> => {
  switch (mode) {
    case 'phone':
      return {
        insetInline: 0,
        bottom: bottomOffset,
        borderStartStartRadius: '16px',
        borderStartEndRadius: '16px',
        maxHeight: '60dvh',
        overflowY: 'auto',
        paddingBottom: 'calc(16px + env(safe-area-inset-bottom))',
        transform: 'none',
      };
    case 'tablet':
      return {
        insetInline: 0,
        marginInline: 'auto',
        bottom: `${READER_BOTTOM_BAR_HEIGHT + 8 + bottomOffset}px`,
        width: 480,
        maxWidth: 'calc(100% - 32px)',
        borderRadius: '16px',
        maxHeight: '60dvh',
        overflowY: 'auto',
      };
    case 'phoneLandscape':
      return {
        top: 0,
        bottom: 0,
        insetInlineEnd: 0,
        width: 360,
        borderRadius: 0,
        overflowY: 'auto',
      };
    default:
      return {
        top: 72,
        insetInlineEnd: 16,
        width: 400,
        borderRadius: '12px',
        maxHeight: '80dvh',
        overflowY: 'auto',
      };
  }
};

interface DisplaySheetProps {
  mode: ReaderLayoutMode;
  // Height of the TTS bar under the bottom of the viewport, which the phone and tablet sheets clear
  bottomOffset: number;
  onClose: () => void;
  onCustomize: () => void;
  onAllSettings: () => void;
}

// Non-modal: no backdrop and no focus trap, so the text stays visible and the shortcuts stay live
const DisplaySheet = ({ mode, bottomOffset, onClose, onCustomize, onAllSettings }: DisplaySheetProps) => {
  const { t } = useTranslation();
  const modules = useReaderSettings().displaySheetModules;
  const closeRef = useRef<HTMLButtonElement>(null);
  const dragStartY = useRef<number | null>(null);
  const [entered, setEntered] = useState(false);
  const touchLayout = mode === 'phone' || mode === 'tablet' || mode === 'phoneLandscape';
  // Touch layouts: header buttons get a 44px target
  const touchTarget = touchLayout ? { minWidth: 44, minHeight: 44 } : undefined;

  // The sheet mounts closed and slides up on the next frame
  useEffect(() => {
    const frame = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  useReturnFocus(closeRef);

  // Dragging the header down closes the sheet on touch layouts; buttons inside the header keep their own clicks
  const handleDragStart = (event: PointerEvent<HTMLDivElement>) => {
    if (!touchLayout || (event.target as Element).closest('button, a')) return;
    dragStartY.current = event.clientY;
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handleDragEnd = (event: PointerEvent<HTMLDivElement>) => {
    if (dragStartY.current !== null && event.clientY - dragStartY.current > DRAG_CLOSE_DISTANCE) onClose();
    dragStartY.current = null;
  };

  return (
    <Paper
      role="dialog"
      data-reader-panel
      aria-label={t('readerDisplay.title')}
      elevation={8}
      sx={{
        position: 'fixed',
        zIndex: (theme) => theme.zIndex.appBar + 2,
        p: 2,
        boxSizing: 'border-box',
        transition: 'transform 0.25s ease-out',
        '@media (prefers-reduced-motion: reduce)': { transition: 'none' },
        ...placement(mode, bottomOffset),
        // Phone only: starts below the screen and slides up
        ...(mode === 'phone' && !entered ? { transform: 'translateY(100%)' } : {}),
      }}
    >
      <Box
        onPointerDown={handleDragStart}
        onPointerUp={handleDragEnd}
        onPointerCancel={() => { dragStartY.current = null; }}
        sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5, touchAction: touchLayout ? 'none' : undefined }}
      >
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, flex: 1, minWidth: 0 }}>
          {t('readerDisplay.title')}
        </Typography>
        <Button size="small" onClick={onAllSettings} sx={touchTarget}>{t('readerDisplay.allSettings')}</Button>
        <IconButton onClick={onCustomize} aria-label={t('readerDisplay.customize')} sx={touchTarget}>
          <EditIcon />
        </IconButton>
        <IconButton ref={closeRef} onClick={onClose} aria-label={t('readerDisplay.close')} sx={touchTarget}>
          <CloseIcon />
        </IconButton>
      </Box>

      <DisplayModuleGrid modules={modules} />
    </Paper>
  );
};

export default DisplaySheet;
