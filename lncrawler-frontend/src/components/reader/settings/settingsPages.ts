import type { ComponentType } from 'react';
import type { SvgIconComponent } from '@mui/icons-material';
import TextFieldsIcon from '@mui/icons-material/TextFields';
import PaletteIcon from '@mui/icons-material/Palette';
import TuneIcon from '@mui/icons-material/Tune';
import TouchAppIcon from '@mui/icons-material/TouchApp';
import KeyboardIcon from '@mui/icons-material/Keyboard';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import RecordVoiceOverIcon from '@mui/icons-material/RecordVoiceOver';
import PictureInPictureAltIcon from '@mui/icons-material/PictureInPictureAlt';
import BackupIcon from '@mui/icons-material/Backup';
import ListeningPage from './pages/ListeningPage';
import VoicePage from './pages/VoicePage';
import BackupPage from './pages/BackupPage';
import DisplayCustomizer from '../display/DisplayCustomizer';
import TextPage from './pages/TextPage';
import ColorsPage from './pages/ColorsPage';
import GesturesPage from './pages/GesturesPage';
import KeyboardPage from './pages/KeyboardPage';
import ReadingPage from './pages/ReadingPage';
import OverlayPage from './pages/OverlayPage';
import type { ScreenZone } from './ScreenZoneMap';

export type SettingsPageId = 'text' | 'colors' | 'custom' | 'touch' | 'keys' | 'reading' | 'overlay' | 'listen' | 'voice' | 'backup';

// Props a page can take when the settings search opens it
interface SettingsPageProps {
  initialZone?: ScreenZone;
}

interface SettingsPageDef {
  titleKey: string;
  Icon: SvgIconComponent;
  Component: ComponentType<SettingsPageProps>;
}

export const SETTINGS_PAGES: Record<SettingsPageId, SettingsPageDef> = {
  text: { titleKey: 'readerSettingsPages.pages.text', Icon: TextFieldsIcon, Component: TextPage },
  colors: { titleKey: 'readerSettingsPages.pages.colors', Icon: PaletteIcon, Component: ColorsPage },
  custom: { titleKey: 'readerSettingsPages.pages.custom', Icon: TuneIcon, Component: DisplayCustomizer },
  touch: { titleKey: 'readerSettingsPages.pages.touch', Icon: TouchAppIcon, Component: GesturesPage },
  keys: { titleKey: 'readerSettingsPages.pages.keys', Icon: KeyboardIcon, Component: KeyboardPage },
  reading: { titleKey: 'readerSettingsPages.pages.reading', Icon: MenuBookIcon, Component: ReadingPage },
  overlay: { titleKey: 'readerSettingsPages.pages.overlay', Icon: PictureInPictureAltIcon, Component: OverlayPage },
  listen: { titleKey: 'readerSettingsPages.pages.listen', Icon: RecordVoiceOverIcon, Component: ListeningPage },
  // A subpage of listen: not in the home or the desktop nav, so no order entry
  voice: { titleKey: 'readerSettingsPages.pages.voice', Icon: RecordVoiceOverIcon, Component: VoicePage },
  backup: { titleKey: 'readerSettingsPages.pages.backup', Icon: BackupIcon, Component: BackupPage },
};

// Order of the desktop nav
export const SETTINGS_PAGE_ORDER: SettingsPageId[] = ['text', 'colors', 'custom', 'keys', 'touch', 'reading', 'overlay', 'backup', 'listen'];
