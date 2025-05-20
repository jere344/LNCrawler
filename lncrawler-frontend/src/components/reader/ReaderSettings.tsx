import {
  Drawer, Box, Typography, IconButton, Divider, Button,
  useTheme, useMediaQuery,
} from '@mui/material';
import Cookies from 'js-cookie';
import CloseIcon from '@mui/icons-material/Close';

// Import our new components
import FontSettings from './settings/FontSettings';
import ColorSettings from './settings/ColorSettings';
import LayoutSettings from './settings/LayoutSettings';
import BehaviorSettings from './settings/BehaviorSettings';
import ReaderNavigation from './controls/ReaderNavigation';

// Define constants for cookie names
const COOKIE_PREFIX = 'lncrawler_reader_';
const COOKIE_EXPIRY = 365; // days

export type EdgeTapBehavior = 'none' | 'scrollUp' | 'scrollDown' | 'chapter';

export interface ReaderSettings {
  fontSize: number;
  fontFamily: string | null;
  textAlign: 'left' | 'center' | 'justify' | 'right';
  fontColor: string | null;
  backgroundColor: string | null;
  margin: number;
  lineSpacing: number;
  readingMode: 'classic' | 'manga' | 'mangaReversed' | 'webtoon';
  dimLevel: number;
  leftEdgeTapBehavior: EdgeTapBehavior;
  rightEdgeTapBehavior: EdgeTapBehavior;
  textSelectable: boolean;
  savePosition: boolean;
}

// Default settings
export const defaultSettings: ReaderSettings = {
  fontSize: 18,
  fontFamily: null,
  textAlign: 'justify',
  fontColor: null,
  backgroundColor: null,
  margin: 0,
  lineSpacing: 1.6,
  readingMode: 'classic',
  dimLevel: 0,
  leftEdgeTapBehavior: 'none',
  rightEdgeTapBehavior: 'none',
  textSelectable: true,
  savePosition: true,
};

export interface ChapterInfo {
  title: string;
  novelTitle: string;
  prevChapter?: number | null;
  nextChapter?: number | null;
}

interface ReaderSettingsProps {
  open: boolean;
  onClose: () => void;
  settings: ReaderSettings;
  onSettingChange: (settings: ReaderSettings) => void;
  chapterInfo: ChapterInfo;
  onNavigate: (type: 'prev' | 'home' | 'next') => void;
}

const ReaderSettings = ({
  open,
  onClose,
  settings,
  onSettingChange,
  chapterInfo,
  onNavigate,
}: ReaderSettingsProps) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  // Helper function to save setting to cookie
  const saveSetting = (key: string, value: any) => {
    Cookies.set(COOKIE_PREFIX + key, JSON.stringify(value), { expires: COOKIE_EXPIRY, sameSite: 'Strict' });
  };

  // Font Settings Handlers
  const handleFontSizeChange = (value: number) => {
    const newSettings = { ...settings, fontSize: value };
    onSettingChange(newSettings);
    saveSetting('fontSize', value);
  };

  const handleFontFamilyChange = (value: string | null) => {
    const newSettings = { ...settings, fontFamily: value };
    onSettingChange(newSettings);
    saveSetting('fontFamily', value);
  };

  const handleTextAlignChange = (value: 'left' | 'center' | 'justify' | 'right') => {
    const newSettings = { ...settings, textAlign: value };
    onSettingChange(newSettings);
    saveSetting('textAlign', value);
  };

  // Color Settings Handlers
  const handleFontColorChange = (color: string | null) => {
    const newSettings = { ...settings, fontColor: color };
    onSettingChange(newSettings);
    saveSetting('fontColor', color);
  };

  const handleBackgroundColorChange = (color: string | null) => {
    const newSettings = { ...settings, backgroundColor: color };
    onSettingChange(newSettings);
    saveSetting('backgroundColor', color);
  };

  const handleDimLevelChange = (level: number) => {
    const newSettings = { ...settings, dimLevel: level };
    onSettingChange(newSettings);
    saveSetting('dimLevel', level);
  };

  // Layout Settings Handlers
  const handleMarginChange = (margin: number) => {
    const newSettings = { ...settings, margin };
    onSettingChange(newSettings);
    saveSetting('margin', margin);
  };

  const handleLineSpacingChange = (lineSpacing: number) => {
    const newSettings = { ...settings, lineSpacing };
    onSettingChange(newSettings);
    saveSetting('lineSpacing', lineSpacing);
  };

  const handleReadingModeChange = (readingMode: string) => {
    const newSettings = { ...settings, readingMode: readingMode as any };
    onSettingChange(newSettings);
    saveSetting('readingMode', readingMode);
  };

  // Behavior Settings Handlers
  const handleEdgeTapChange = (edge: 'left' | 'right', behavior: EdgeTapBehavior) => {
    const key = edge === 'left' ? 'leftEdgeTapBehavior' : 'rightEdgeTapBehavior';
    const newSettings = { ...settings, [key]: behavior };
    onSettingChange(newSettings);
    saveSetting(key, behavior);
  };

  const handleTextSelectableChange = (selectable: boolean) => {
    const newSettings = { ...settings, textSelectable: selectable };
    onSettingChange(newSettings);
    saveSetting('textSelectable', selectable);
  };

  const handleSavePositionChange = (save: boolean) => {
    const newSettings = { ...settings, savePosition: save };
    onSettingChange(newSettings);
    saveSetting('savePosition', save);
  };

  const resetDefaults = () => {
    onSettingChange(defaultSettings);
    Object.entries(defaultSettings).forEach(([key, value]) => {
      saveSetting(key, value);
    });
  };

  return (
    <Drawer 
      anchor={isMobile ? "bottom" : "right"} 
      open={open} 
      onClose={onClose}
      PaperProps={{
        sx: {
          width: isMobile ? '100%' : '350px',
          maxHeight: isMobile ? '60vh' : '100%',
          borderTopLeftRadius: isMobile ? '16px' : 0,
          borderTopRightRadius: isMobile ? '16px' : 0,
          padding: 2,
          overflow: 'auto',
          zIndex: theme.zIndex.drawer,
          boxShadow: 3,
        }
      }}
    >
      <Box sx={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        mx: -2,
        mt: -2,
        p: 2,
        pb: 0.5,
        position: 'sticky',
        top: "-30px",
        width: 'calc(100% + 32px)',
        zIndex: 2,
        backgroundColor: theme.palette.background.paper,
      }}>
        <Typography variant="h6">Reader Settings</Typography>
        <IconButton onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </Box>

      <Divider sx={{ mb: 2 }} />

      {/* Navigation Controls */}
      <ReaderNavigation 
        prevChapter={chapterInfo.prevChapter}
        nextChapter={chapterInfo.nextChapter}
        onPrevious={() => onNavigate('prev')}
        onNext={() => onNavigate('next')}
        onHome={() => onNavigate('home')}
      />

      <Divider sx={{ mb: 2 }} />

      {/* Font Settings */}
      <FontSettings 
        fontSize={settings.fontSize}
        fontFamily={settings.fontFamily}
        textAlign={settings.textAlign}
        onFontSizeChange={handleFontSizeChange}
        onFontFamilyChange={handleFontFamilyChange}
        onTextAlignChange={handleTextAlignChange}
      />

      <Divider sx={{ mb: 2 }} />

      {/* Color Settings */}
      <ColorSettings 
        fontColor={settings.fontColor}
        backgroundColor={settings.backgroundColor}
        dimLevel={settings.dimLevel}
        onFontColorChange={handleFontColorChange}
        onBackgroundColorChange={handleBackgroundColorChange}
        onDimLevelChange={handleDimLevelChange}
      />

      <Divider sx={{ mb: 2 }} />

      {/* Layout Settings */}
      <LayoutSettings 
        margin={settings.margin}
        lineSpacing={settings.lineSpacing}
        readingMode={settings.readingMode}
        onMarginChange={handleMarginChange}
        onLineSpacingChange={handleLineSpacingChange}
        onReadingModeChange={handleReadingModeChange}
      />

      <Divider sx={{ my: 2 }} />

      {/* Behavior Settings */}
      <BehaviorSettings 
        leftEdgeTapBehavior={settings.leftEdgeTapBehavior}
        rightEdgeTapBehavior={settings.rightEdgeTapBehavior}
        textSelectable={settings.textSelectable}
        savePosition={settings.savePosition}
        onEdgeTapChange={handleEdgeTapChange}
        onTextSelectableChange={handleTextSelectableChange}
        onSavePositionChange={handleSavePositionChange}
      />

      {/* Reset Button */}
      <Button
        variant="contained"
        color="secondary"
        fullWidth
        onClick={resetDefaults}
      >
        Reset to Defaults
      </Button>
    </Drawer>
  );
};

export default ReaderSettings;
