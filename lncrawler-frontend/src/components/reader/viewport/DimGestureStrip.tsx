import { useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { Box, Typography } from '@mui/material';
import type { DimGestureSide } from '../readerSettingsSchema';
import { updateReaderSetting } from '../readerSettingsStore';
import { dimBandWidth, dimLevelFromDrag } from '../readerGeometry';
import { useViewportSize } from '../hooks/useViewportSize';
import type { ReaderTapProps } from '../hooks/useReaderTapInput';

// Vertical movement before a press becomes a drag
const DRAG_START_PX = 8;
const HUD_GAP = 8;

interface DimGestureStripProps {
  side: Exclude<DimGestureSide, 'off'>;
  savedWidth: number;
  dimLevel: number;
  tapProps: ReaderTapProps;
  // A press that never became a drag is a tap, decided the same way as a tap on the text
  onTap: (x: number, width: number, target: EventTarget) => void;
}

// A strip at one screen edge: a touch or pen drag down darkens, up lightens. Mouse is ignored.
const DimGestureStrip = ({ side, savedWidth, dimLevel, tapProps, onTap }: DimGestureStripProps) => {
  const { width: viewportWidth } = useViewportSize();
  const bandPercent = dimBandWidth(savedWidth, viewportWidth);
  // The press in progress: its pointer, where and from what level it started, and whether it became a drag
  const pressRef = useRef<{ pointerId: number; startY: number; startLevel: number; dragging: boolean } | null>(null);
  const [dragging, setDragging] = useState(false);

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.pointerType === 'mouse') return;
    tapProps.onPointerDown?.(e);
    e.currentTarget.setPointerCapture(e.pointerId);
    pressRef.current = { pointerId: e.pointerId, startY: e.clientY, startLevel: dimLevel, dragging: false };
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const press = pressRef.current;
    if (!press || press.pointerId !== e.pointerId) return;
    tapProps.onPointerMove?.(e);
    const dy = e.clientY - press.startY;
    if (!press.dragging) {
      if (Math.abs(dy) < DRAG_START_PX) return;
      press.dragging = true;
      setDragging(true);
    }
    const level = dimLevelFromDrag(press.startLevel, dy);
    if (level !== dimLevel) updateReaderSetting('dimLevel', level);
  };

  const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    const press = pressRef.current;
    if (!press || press.pointerId !== e.pointerId) return;
    pressRef.current = null;
    setDragging(false);
    tapProps.onPointerUp?.(e);
    if (!press.dragging) onTap(e.clientX, viewportWidth, e.target);
  };

  const onPointerCancel = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (pressRef.current?.pointerId !== e.pointerId) return;
    pressRef.current = null;
    setDragging(false);
    tapProps.onPointerCancel?.(e);
  };

  // The HUD shows visibility, not dimming: 100% is undimmed, and it rises as the finger moves up
  const visibility = 100 - dimLevel;

  return (
    <>
      <Box
        aria-hidden
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerCancel}
        sx={{
          position: 'fixed',
          top: 0,
          bottom: 0,
          [side]: 0,
          width: `${bandPercent}%`,
          touchAction: 'none',
          // Below the site header, so its controls stay tappable; the HUD above keeps its own layer
          zIndex: (theme) => theme.zIndex.appBar - 1,
        }}
      />

      {dragging && (
        <Box
          role="none"
          aria-hidden
          sx={{
            position: 'fixed',
            top: '50%',
            transform: 'translateY(-50%)',
            [side === 'left' ? 'left' : 'right']: `calc(${bandPercent}% + ${HUD_GAP}px)`,
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            px: 1,
            py: 0.5,
            borderRadius: 1,
            bgcolor: 'background.paper',
            boxShadow: 2,
            pointerEvents: 'none',
            zIndex: (theme) => theme.zIndex.appBar + 2,
          }}
        >
          <Box sx={{ position: 'relative', width: 6, height: 120, borderRadius: 3, overflow: 'hidden', bgcolor: 'action.disabledBackground' }}>
            <Box sx={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: `${visibility}%`, bgcolor: 'text.primary' }} />
          </Box>
          <Typography variant="body2" component="span" sx={{ minWidth: '3em' }}>{visibility}%</Typography>
        </Box>
      )}
    </>
  );
};

export default DimGestureStrip;
