import type { SettingsPageId } from './settings/settingsPages';

// The panels that open over the reader. One at a time; 'none' is the reader alone.
export type ReaderPanel = 'none' | 'display' | 'customize' | 'settings' | 'chapters';

// The layers open over the reader. They live in the state of the history entry, one entry per layer,
// so Back climbs them one at a time.
export interface ReaderLayers {
  panel: ReaderPanel;
  // Settings pages pushed over the settings home, bottom first; the last one is on screen
  pages: SettingsPageId[];
  // The search field has a query, which is a layer of its own above the pages
  searching: boolean;
  // History entries pushed above the reader's own entry for these layers
  depth: number;
}

// Key of the layers in location.state
const STATE_KEY = 'readerLayers';

export const CLOSED_LAYERS: ReaderLayers = { panel: 'none', pages: [], searching: false, depth: 0 };

const PANELS: ReaderPanel[] = ['display', 'customize', 'settings', 'chapters'];

// Every settings page: a saved state with any other id is malformed
const PAGE_IDS: Record<SettingsPageId, true> = {
  text: true,
  colors: true,
  custom: true,
  touch: true,
  keys: true,
  reading: true,
  listen: true,
  voice: true,
  backup: true,
};

// A subpage sits over its parent page, which stays on screen beneath it
const PARENT_PAGE: Partial<Record<SettingsPageId, SettingsPageId>> = { voice: 'listen' };

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isPanel = (value: unknown): value is ReaderPanel =>
  PANELS.some((panel) => panel === value);

const isPageId = (value: unknown): value is SettingsPageId =>
  typeof value === 'string' && Object.prototype.hasOwnProperty.call(PAGE_IDS, value);

// Reads the layers from a history entry's state. Missing or malformed state reads as closed.
export function readLayers(state: unknown): ReaderLayers {
  const saved = isRecord(state) ? state[STATE_KEY] : undefined;
  if (!isRecord(saved)) return CLOSED_LAYERS;

  const { panel, pages, searching, depth } = saved;
  // An open panel was pushed above the reader's entry, so its depth is at least 1
  if (!isPanel(panel) || typeof depth !== 'number' || !Number.isInteger(depth) || depth < 1) return CLOSED_LAYERS;

  return {
    panel,
    pages: Array.isArray(pages) ? pages.filter(isPageId) : [],
    searching: searching === true,
    depth,
  };
}

// The state for a history entry: its other keys are kept, and the layers are set
export function writeLayers(state: unknown, layers: ReaderLayers): Record<string, unknown> {
  return { ...(isRecord(state) ? state : {}), [STATE_KEY]: layers };
}

// A panel opened over `base`: one entry above it
export function openLayer(
  base: ReaderLayers,
  panel: Exclude<ReaderPanel, 'none'>,
  pages: SettingsPageId[] = [],
): ReaderLayers {
  return { panel, pages, searching: false, depth: base.depth + 1 };
}

// A settings page pushed over the current one: one entry more
export function addPage(layers: ReaderLayers, page: SettingsPageId): ReaderLayers {
  return { ...layers, pages: [...layers.pages, page], depth: layers.depth + 1 };
}

// The first query of the search field: one entry more
export function addSearch(layers: ReaderLayers): ReaderLayers {
  return { ...layers, searching: true, depth: layers.depth + 1 };
}

// The pages a page needs on screen: its parent first, when it is a subpage
export function pageStack(page: SettingsPageId): SettingsPageId[] {
  const parent = PARENT_PAGE[page];
  return parent ? [parent, page] : [page];
}

// Shows `page` (or the home) in place of the current entry, which ends the search. The depth stays.
export function replacePages(layers: ReaderLayers, page: SettingsPageId | null): ReaderLayers {
  return { ...layers, pages: page ? pageStack(page) : [], searching: false };
}

// Shows `page` in place of the entry below a search, and drops the search entry: the depth falls by one
export function replaceBelowSearch(layers: ReaderLayers, page: SettingsPageId | null): ReaderLayers {
  return replacePages({ ...layers, searching: false, depth: layers.depth - 1 }, page);
}
