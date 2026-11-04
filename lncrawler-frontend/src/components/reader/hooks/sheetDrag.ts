import { useRef, type PointerEvent } from 'react';

// A drag this many px up expands a sheet, and this many px down shrinks it or closes it
export const SHEET_SNAP_DISTANCE = 30;
// A pointer that moves less than this many px is a tap
export const SHEET_TAP_DISTANCE = 6;

// What a drag does to a sheet; null for a drag too short to count
type SheetDragResult = 'expand' | 'shrink' | 'close' | 'stopComposing' | 'toggle' | null;

// What a drag of `dy` px (downward is positive) does to a sheet that is full height or not. A composer open in it closes first.
export const sheetDragResult = (dy: number, full: boolean, composing = false): SheetDragResult => {
  if (dy < -SHEET_SNAP_DISTANCE) return 'expand';
  if (dy > SHEET_SNAP_DISTANCE) {
    if (composing) return 'stopComposing';
    return full ? 'shrink' : 'close';
  }
  if (Math.abs(dy) < SHEET_TAP_DISTANCE) return 'toggle';
  return null;
};

// Follows a pointer from down to up on a drag handle, and reports how far it moved in px.
// `canStart` decides whether a press begins a drag at all.
export function usePointerDragY(
  onEnd: (dy: number) => void,
  canStart: (event: PointerEvent<HTMLElement>) => boolean = () => true,
) {
  const startY = useRef<number | null>(null);

  return {
    onPointerDown: (event: PointerEvent<HTMLElement>) => {
      if (!canStart(event)) return;
      startY.current = event.clientY;
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    onPointerUp: (event: PointerEvent<HTMLElement>) => {
      const start = startY.current;
      startY.current = null;
      if (start !== null) onEnd(event.clientY - start);
    },
    onPointerCancel: () => {
      startY.current = null;
    },
  };
}
