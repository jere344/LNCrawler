import type { ReaderLayoutMode } from '../hooks/useReaderLayout';
import type { ReaderPanel } from '../hooks/useReaderPanels';

// Width of a side panel in px; null on phones, where the panel covers the whole screen
export function panelWidth(mode: ReaderLayoutMode): number | null {
  switch (mode) {
    case 'phone':
      return null;
    case 'tablet':
    case 'phoneLandscape':
      return 400;
    default:
      return 600;
  }
}

// Width of the chapter list at the start edge, off phones (on phones it overlays the text)
export const CHAPTER_LIST_WIDTH = 360;

// Space the text and bars keep clear of an open panel at the end of the screen
export function reservedEnd(panel: ReaderPanel, mode: ReaderLayoutMode): number {
  if (panel === 'display') return mode === 'phoneLandscape' ? 360 : 0;
  if (panel === 'settings' || panel === 'customize') return panelWidth(mode) ?? 0;
  return 0;
}

// Space the text and bars keep clear of an open panel at the start of the screen
export function reservedStart(panel: ReaderPanel, mode: ReaderLayoutMode): number {
  return panel === 'chapters' && mode !== 'phone' ? CHAPTER_LIST_WIDTH : 0;
}

// End margin that keeps a column clear of a reserved width. The app's outer container is 1200px wide and centred,
// so the gutter beside it already counts toward the reserved width.
export function reservedMargin(px: number): string | 0 {
  return px ? `max(0px, calc(${px}px - max(0px, (100vw - 1200px) / 2)))` : 0;
}
