import type { DisplayModule } from '../readerSettingsSchema';
import type { ReaderLayoutMode } from '../hooks/useReaderLayout';
import { READER_BOTTOM_BAR_HEIGHT } from '../controls/readerBarTypes';

// Half modules share a line with their neighbour; full modules take the whole line
export const MODULE_LAYOUT: Record<DisplayModule, { half: boolean; height: number }> = {
  size: { half: true, height: 48 },
  line: { half: true, height: 48 },
  para: { half: true, height: 48 },
  margin: { half: true, height: 48 },
  indent: { half: true, height: 48 },
  align: { half: false, height: 48 },
  theme: { half: false, height: 62 },
  font: { half: false, height: 48 },
  dim: { half: false, height: 44 },
  warm: { half: false, height: 44 },
};

const SHEET_HEADER_HEIGHT = 44;
const SHEET_PADDING = 14;
const ROW_GAP = 10;
// Tablet sheets sit above the bottom bar, which takes this much room
const TABLET_BOTTOM_SPACE = READER_BOTTOM_BAR_HEIGHT;
// The sheet may take at most this share of the viewport height on phones and tablets
const MAX_SHEET_RATIO = 0.58;

// Groups the modules into lines: two consecutive half modules share a line
export function pairRows(modules: DisplayModule[]): DisplayModule[][] {
  const rows: DisplayModule[][] = [];
  for (let i = 0; i < modules.length; i++) {
    const current = modules[i];
    const next = modules[i + 1];
    if (MODULE_LAYOUT[current].half && next && MODULE_LAYOUT[next].half) {
      rows.push([current, next]);
      i++;
    } else {
      rows.push([current]);
    }
  }
  return rows;
}

// Height of the sheet with these modules, header and padding included
export function sheetHeight(modules: DisplayModule[]): number {
  const rowsHeight = pairRows(modules).reduce(
    (sum, row) => sum + Math.max(...row.map((module) => MODULE_LAYOUT[module].height)) + ROW_GAP,
    0
  );
  return SHEET_HEADER_HEIGHT + rowsHeight + SHEET_PADDING;
}

// Whether the sheet fits the viewport. Phone landscape and desktop never run out of room.
export function fitsInSheet(modules: DisplayModule[], viewportHeight: number, mode: ReaderLayoutMode): boolean {
  if (mode === 'phoneLandscape' || mode === 'desktop') return true;
  const height = sheetHeight(modules) + (mode === 'tablet' ? TABLET_BOTTOM_SPACE : 0);
  return height / viewportHeight <= MAX_SHEET_RATIO;
}
