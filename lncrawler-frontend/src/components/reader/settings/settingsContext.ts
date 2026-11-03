import { createContext, useContext } from 'react';
import type { ReaderLayoutMode } from '../hooks/useReaderLayout';
import type { SettingsPageId } from './settingsPages';

// What the settings pages need from the reader, provided by the settings panel
interface SettingsContextValue {
  mode: ReaderLayoutMode;
  // Language of the novel being read (used by the voice settings)
  novelLanguage: string;
  // Called before a voice preview plays, so the player can pause
  onBeforePreview?: () => void;
  // The current chapter has a narrated audiobook recording
  hasNarration: boolean;
  // The number of the chapter being read; undefined when no chapter is open
  chapterNumber?: number;
  // Opens a subpage of the page on screen (voice, from listening)
  onOpenPage: (page: SettingsPageId) => void;
  // A signed-in user, who can mark chapters as read
  isAuthenticated: boolean;
}

export const SettingsContext = createContext<SettingsContextValue>({
  mode: 'phone',
  novelLanguage: '',
  hasNarration: false,
  onOpenPage: () => undefined,
  isAuthenticated: false,
});

export const useSettingsContext = () => useContext(SettingsContext);
