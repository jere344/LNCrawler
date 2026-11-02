import { createContext, useContext } from 'react';
import type { ReaderLayoutMode } from '../hooks/useReaderLayout';

// What the settings pages need from the reader, provided by the settings panel
interface SettingsContextValue {
  mode: ReaderLayoutMode;
  // Language of the novel being read (used by the voice settings)
  novelLanguage: string;
  // Called before a voice preview plays, so the player can pause
  onBeforePreview?: () => void;
  // The current chapter has a narrated audiobook recording
  hasNarration: boolean;
  // A signed-in user, who can mark chapters as read
  isAuthenticated: boolean;
}

export const SettingsContext = createContext<SettingsContextValue>({
  mode: 'phone',
  novelLanguage: '',
  hasNarration: false,
  isAuthenticated: false,
});

export const useSettingsContext = () => useContext(SettingsContext);
