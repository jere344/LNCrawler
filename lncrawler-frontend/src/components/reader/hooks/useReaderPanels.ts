import { useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import type { SettingsPageId } from '../settings/settingsPages';
import {
  CLOSED_LAYERS,
  addPage,
  addSearch,
  openLayer,
  readLayers,
  replaceBelowSearch,
  replacePages,
  writeLayers,
  type ReaderLayers,
} from '../readerLayers';

export type { ReaderPanel } from '../readerLayers';

interface ReaderPanelsOptions {
  // Desktop shows its settings pages side by side, so a page there is not a level of its own
  isDesktop: boolean;
}

// The panels open over the reader. Their state lives in the history: each layer is one entry above
// the reader's own, so Back climbs them one at a time. The bars (controls) are not a layer.
export function useReaderPanels({ isDesktop }: ReaderPanelsOptions) {
  const navigate = useNavigate();
  const location = useLocation();
  const layers = readLayers(location.state);
  const { panel, pages, searching, depth } = layers;

  // Stores the layers on a new entry (push) or on the current one (replace)
  const write = (next: ReaderLayers, replace = false) => {
    navigate(location, { state: writeLayers(location.state, next), replace });
  };
  const push = (next: ReaderLayers) => write(next);

  // Up one level, the same as Back
  const popPage = () => {
    if (depth > 0) navigate(-1);
  };
  // Closes every layer at once, from any depth
  const closePanel = () => {
    if (depth > 0) navigate(-depth);
  };

  // Work waiting on the history: a callback to run once the layers are closed, and a layer to push
  // once the entry below it is shown. Both run in the effect below, after that entry has committed.
  const pendingRun = useRef<(() => void) | null>(null);
  const pendingPush = useRef<ReaderLayers | null>(null);
  const pendingReplace = useRef<ReaderLayers | null>(null);

  // Runs `run` once every layer is closed and the reader's own entry is shown again.
  // A request made while the layers are already closing replaces the pending one.
  const closeThen = (run: () => void) => {
    if (depth === 0) {
      run();
      return;
    }
    const closing = pendingRun.current !== null;
    pendingRun.current = run;
    if (!closing) navigate(-depth);
  };

  useEffect(() => {
    // The push waits for the entry below it to commit: two navigations in a row would not both land
    const next = pendingPush.current;
    if (next && depth === next.depth - 1) {
      pendingPush.current = null;
      navigate(location, { state: writeLayers(location.state, next) });
    }
    // The replace waits the same way, for the entry below a search to be shown
    const replaced = pendingReplace.current;
    if (replaced && depth === replaced.depth) {
      pendingReplace.current = null;
      navigate(location, { state: writeLayers(location.state, replaced), replace: true });
    }
    if (depth === 0 && pendingRun.current) {
      const run = pendingRun.current;
      pendingRun.current = null;
      run();
    }
  }, [location, depth, navigate]);

  // Opens `target`, or closes it when it is already open. Another panel closes first, so only one is ever in the history.
  const togglePanel = (target: 'display' | 'chapters') => {
    if (panel === target) closePanel();
    else if (panel === 'none') push(openLayer(layers, target));
    else {
      pendingPush.current = openLayer(CLOSED_LAYERS, target);
      closePanel();
    }
  };
  const toggleDisplay = () => togglePanel('display');
  const toggleChapters = () => togglePanel('chapters');

  // The TTS tune button opens a page: on stack layouts it sits above the home, on desktop it is the nav's page
  const openSettings = ({ page }: { page?: SettingsPageId } = {}) => {
    if (!page) {
      push(openLayer(layers, 'settings'));
    } else if (isDesktop) {
      push(openLayer(layers, 'settings', [page]));
    } else {
      // Stack layouts: the home is an entry of its own, so Back from the page returns to it
      const home = openLayer(layers, 'settings');
      pendingPush.current = addPage(home, page);
      push(home);
    }
  };
  // Customize is a level above the display sheet, so going back returns there
  const openCustomize = () => {
    push(openLayer(layers, 'customize', ['custom']));
  };
  const pushPage = (page: SettingsPageId) => {
    push(addPage(layers, page));
  };
  // Replaces the current entry: a desktop nav choice, or a search result. Null is the home.
  // On desktop a search is an entry of its own: it is dropped and the entry below is replaced, so Back closes.
  const setDeskPage = (page: SettingsPageId | null) => {
    if (searching && isDesktop) {
      pendingReplace.current = replaceBelowSearch(layers, page);
      navigate(-1);
      return;
    }
    write(replacePages(layers, page), true);
  };
  const startSearch = () => {
    push(addSearch(layers));
  };

  return {
    panel,
    pages,
    searching,
    toggleDisplay,
    toggleChapters,
    openSettings,
    openCustomize,
    closePanel,
    popPage,
    pushPage,
    setDeskPage,
    startSearch,
    closeThen,
  };
}
