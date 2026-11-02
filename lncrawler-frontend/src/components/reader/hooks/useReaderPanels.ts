import { useState } from 'react';
import type { SettingsPageId } from '../settings/settingsPages';

export type ReaderPanel = 'none' | 'display' | 'customize' | 'settings';

// The open panel (one at a time). The bars' visibility is owned by the reader.
export function useReaderPanels() {
  const [panel, setPanel] = useState<ReaderPanel>('none');
  // The settings page to open first, when the settings panel opens on one (the TTS tune button)
  const [settingsPage, setSettingsPage] = useState<SettingsPageId | undefined>(undefined);

  const toggleDisplay = () => {
    setSettingsPage(undefined);
    setPanel((current) => (current === 'display' ? 'none' : 'display'));
  };
  const openSettings = ({ page }: { page?: SettingsPageId } = {}) => {
    setSettingsPage(page);
    setPanel('settings');
  };
  // Customize is only reachable from the display sheet, so going back returns there
  const openCustomize = () => {
    setSettingsPage(undefined);
    setPanel('customize');
  };
  const closeCustomize = () => {
    setPanel('display');
  };
  const closePanel = () => {
    setSettingsPage(undefined);
    setPanel('none');
  };

  return {
    panel,
    settingsPage,
    toggleDisplay,
    openSettings,
    openCustomize,
    closeCustomize,
    closePanel,
  };
}
