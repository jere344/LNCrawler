import {
  Drawer, Box, Typography, IconButton, Divider, Button,
  useTheme, useMediaQuery, Stack, Dialog, DialogTitle, 
  DialogContent, DialogContentText, DialogActions,
} from '@mui/material';
import { useState } from 'react';
import Cookies from 'js-cookie';
import CloseIcon from '@mui/icons-material/Close';
import DownloadIcon from '@mui/icons-material/Download';
import UploadIcon from '@mui/icons-material/Upload';
import TextFieldsIcon from '@mui/icons-material/TextFields';
import PaletteIcon from '@mui/icons-material/Palette';
import ViewColumnIcon from '@mui/icons-material/ViewColumn';
import TouchAppIcon from '@mui/icons-material/TouchApp';
import SettingsIcon from '@mui/icons-material/Settings';
import MenuBookIcon from '@mui/icons-material/MenuBook';

// Import our new components
import FontSettings from './settings/FontSettings';
import ColorSettings from './settings/ColorSettings';
import LayoutSettings from './settings/LayoutSettings';
import BehaviorSettings from './settings/BehaviorSettings';
import GestureSettings from './settings/GestureSettings';
import PageSettings from './settings/PageSettings';
import ReaderNavigation from './controls/ReaderNavigation';
import SettingsSection from './SettingsSection';

// Define constants for cookie names
const COOKIE_PREFIX = 'lncrawler_reader_';
const COOKIE_EXPIRY = 365; // days

export type EdgeTapBehavior = 'none' | 'scrollUp' | 'scrollDown' | 'chapter';
export type MarkReadBehavior = 'none' | 'button' | 'automatic' | 'buttonAutomatic';
export type SwipeGesture = 'none' | 'prevChapter' | 'nextChapter';

export interface ReaderSettings {
  fontSize: number;
  fontFamily: string | null;
  textAlign: 'left' | 'center' | 'justify' | 'right';
  fontColor: string | null;
  backgroundColor: string | null;
  margin: number;
  lineSpacing: number;
  wordSpacing: number;
  letterSpacing: number;
  dimLevel: number;
  leftEdgeTapBehavior: EdgeTapBehavior;
  rightEdgeTapBehavior: EdgeTapBehavior;
  textSelectable: boolean;
  savePosition: boolean;
  markReadBehavior: MarkReadBehavior;
  keyboardNavigation: boolean;
  swipeLeftGesture: SwipeGesture;
  swipeRightGesture: SwipeGesture;
  hideScrollbar: boolean;
  paragraphIndent: boolean;
  paragraphSpacing: number;
  centerTapToOpenSettings: boolean;
  pageMode: boolean;
  showPages: boolean;
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
  wordSpacing: 0,
  letterSpacing: 0,
  dimLevel: 0,
  leftEdgeTapBehavior: 'none',
  rightEdgeTapBehavior: 'none',
  textSelectable: true,
  savePosition: true,
  markReadBehavior: 'buttonAutomatic',
  keyboardNavigation: true,
  swipeLeftGesture: 'nextChapter',
  swipeRightGesture: 'prevChapter',
  hideScrollbar: false,
  paragraphIndent: false,
  paragraphSpacing: 1,
  centerTapToOpenSettings: true,
  pageMode: false,
  showPages: true,
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
  isAuthenticated?: boolean;
  prevUrl?: string;
  nextUrl?: string;
  homeUrl?: string;
}

const ReaderSettings = ({
  open,
  onClose,
  settings,
  onSettingChange,
  chapterInfo,
  onNavigate,
  isAuthenticated = false,
  prevUrl,
  nextUrl,
  homeUrl,
}: ReaderSettingsProps) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);

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

  const handleHideScrollbarChange = (hide: boolean) => {
    const newSettings = { ...settings, hideScrollbar: hide };
    onSettingChange(newSettings);
    saveSetting('hideScrollbar', hide);
  };

  const handleWordSpacingChange = (spacing: number) => {
    const newSettings = { ...settings, wordSpacing: spacing };
    onSettingChange(newSettings);
    saveSetting('wordSpacing', spacing);
  };

  const handleLetterSpacingChange = (spacing: number) => {
    const newSettings = { ...settings, letterSpacing: spacing };
    onSettingChange(newSettings);
    saveSetting('letterSpacing', spacing);
  };

  const handleParagraphIndentChange = (indent: boolean) => {
    const newSettings = { ...settings, paragraphIndent: indent };
    onSettingChange(newSettings);
    saveSetting('paragraphIndent', indent);
  };

  const handleParagraphSpacingChange = (spacing: number) => {
    const newSettings = { ...settings, paragraphSpacing: spacing };
    onSettingChange(newSettings);
    saveSetting('paragraphSpacing', spacing);
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
  
  const handleMarkReadBehaviorChange = (behavior: MarkReadBehavior) => {
    const newSettings = { ...settings, markReadBehavior: behavior };
    onSettingChange(newSettings);
    saveSetting('markReadBehavior', behavior);
  };

  const handleKeyboardNavigationChange = (enabled: boolean) => {
    const newSettings = { ...settings, keyboardNavigation: enabled };
    onSettingChange(newSettings);
    saveSetting('keyboardNavigation', enabled);
  };

  const handleCenterTapToOpenSettingsChange = (enabled: boolean) => {
    const newSettings = { ...settings, centerTapToOpenSettings: enabled };
    onSettingChange(newSettings);
    saveSetting('centerTapToOpenSettings', enabled);
  };

  // Gesture Settings Handlers
  const handleSwipeGestureChange = (direction: 'left' | 'right', gesture: SwipeGesture) => {
    const key = direction === 'left' ? 'swipeLeftGesture' : 'swipeRightGesture';
    const newSettings = { ...settings, [key]: gesture };
    onSettingChange(newSettings);
    saveSetting(key, gesture);
  };

  // Page Settings Handlers
  const handlePageModeChange = (enabled: boolean) => {
    const newSettings = { ...settings, pageMode: enabled };
    onSettingChange(newSettings);
    saveSetting('pageMode', enabled);
  };

  const handleShowPagesChange = (show: boolean) => {
    const newSettings = { ...settings, showPages: show };
    onSettingChange(newSettings);
    saveSetting('showPages', show);
  };

  const resetDefaults = () => {
    onSettingChange(defaultSettings);
    Object.entries(defaultSettings).forEach(([key, value]) => {
      saveSetting(key, value);
    });
    setResetConfirmOpen(false);
  };

  const handleResetClick = () => {
    setResetConfirmOpen(true);
  };

  const handleResetCancel = () => {
    setResetConfirmOpen(false);
  };

  // Export settings to JSON file
  const exportSettings = () => {
    const settingsData = {
      ...settings,
      exportDate: new Date().toISOString(),
      version: '1.0'
    };
    
    const blob = new Blob([JSON.stringify(settingsData, null, 2)], {
      type: 'application/json'
    });
    
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `lncrawler-reader-settings-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  // Import settings from JSON file
  const importSettings = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    
    input.onchange = (event) => {
      const file = (event.target as HTMLInputElement).files?.[0];
      if (!file) return;
      
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const importedData = JSON.parse(e.target?.result as string);
          
          // Validate that the imported data has the expected structure
          const validKeys = Object.keys(defaultSettings);
          const importedSettings: Partial<ReaderSettings> = {};
          
          validKeys.forEach(key => {
            if (key in importedData) {
              importedSettings[key as keyof ReaderSettings] = importedData[key];
            }
          });
          
          // Merge with default settings to ensure all properties exist
          const newSettings = { ...defaultSettings, ...importedSettings };
          
          // Update state and save to cookies
          onSettingChange(newSettings);
          Object.entries(newSettings).forEach(([key, value]) => {
            saveSetting(key, value);
          });
          
        } catch (error) {
          console.error('Failed to import settings:', error);
          alert('Failed to import settings. Please check that the file is a valid settings export.');
        }
      };
      
      reader.readAsText(file);
    };
    
    input.click();
  };

  return (
    <>
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
            paddingRight: 3,
            overflow: 'auto',
            zIndex: theme.zIndex.drawer,
            boxShadow: 3,
            backgroundColor: theme.palette.background.default,
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

        {/* Navigation Controls - Always visible */}
        <ReaderNavigation 
          prevChapter={chapterInfo.prevChapter}
          nextChapter={chapterInfo.nextChapter}
          onPrevious={() => onNavigate('prev')}
          onNext={() => onNavigate('next')}
          onHome={() => onNavigate('home')}
          prevUrl={prevUrl}
          nextUrl={nextUrl}
          homeUrl={homeUrl}
        />

        <Divider sx={{ mb: 2 }} />

        {/* Font Settings */}
        <SettingsSection 
          title="Font" 
          icon={<TextFieldsIcon color="primary" />}
          defaultExpanded
        >
          <FontSettings 
            fontSize={settings.fontSize}
            fontFamily={settings.fontFamily}
            textAlign={settings.textAlign}
            onFontSizeChange={handleFontSizeChange}
            onFontFamilyChange={handleFontFamilyChange}
            onTextAlignChange={handleTextAlignChange}
          />
        </SettingsSection>

        {/* Color Settings */}
        <SettingsSection 
          title="Colors" 
          icon={<PaletteIcon color="primary" />}
        >
          <ColorSettings 
            fontColor={settings.fontColor}
            backgroundColor={settings.backgroundColor}
            dimLevel={settings.dimLevel}
            onFontColorChange={handleFontColorChange}
            onBackgroundColorChange={handleBackgroundColorChange}
            onDimLevelChange={handleDimLevelChange}
          />
        </SettingsSection>

        {/* Layout Settings */}
        <SettingsSection 
          title="Layout" 
          icon={<ViewColumnIcon color="primary" />}
        >
          <LayoutSettings 
            margin={settings.margin}
            lineSpacing={settings.lineSpacing}
            wordSpacing={settings.wordSpacing}
            letterSpacing={settings.letterSpacing}
            hideScrollbar={settings.hideScrollbar}
            paragraphIndent={settings.paragraphIndent}
            paragraphSpacing={settings.paragraphSpacing}
            onMarginChange={handleMarginChange}
            onLineSpacingChange={handleLineSpacingChange}
            onWordSpacingChange={handleWordSpacingChange}
            onLetterSpacingChange={handleLetterSpacingChange}
            onHideScrollbarChange={handleHideScrollbarChange}
            onParagraphIndentChange={handleParagraphIndentChange}
            onParagraphSpacingChange={handleParagraphSpacingChange}
          />
        </SettingsSection>

        {/* Gesture Settings */}
        <SettingsSection 
          title="Gestures" 
          icon={<TouchAppIcon color="primary" />}
        >
          <GestureSettings
            swipeLeftGesture={settings.swipeLeftGesture}
            swipeRightGesture={settings.swipeRightGesture}
            onSwipeGestureChange={handleSwipeGestureChange}
          />
        </SettingsSection>

        {/* Behavior Settings */}
        <SettingsSection 
          title="Behavior" 
          icon={<SettingsIcon color="primary" />}
        >
          <BehaviorSettings 
            leftEdgeTapBehavior={settings.leftEdgeTapBehavior}
            rightEdgeTapBehavior={settings.rightEdgeTapBehavior}
            textSelectable={settings.textSelectable}
            savePosition={settings.savePosition}
            markReadBehavior={settings.markReadBehavior}
            keyboardNavigation={settings.keyboardNavigation}
            centerTapToOpenSettings={settings.centerTapToOpenSettings}
            onEdgeTapChange={handleEdgeTapChange}
            onTextSelectableChange={handleTextSelectableChange}
            onSavePositionChange={handleSavePositionChange}
            onMarkReadBehaviorChange={handleMarkReadBehaviorChange}
            onKeyboardNavigationChange={handleKeyboardNavigationChange}
            onCenterTapToOpenSettingsChange={handleCenterTapToOpenSettingsChange}
            isAuthenticated={isAuthenticated}
          />
        </SettingsSection>

        {/* Page Mode Settings */}
        <SettingsSection 
          title="Page Mode" 
          icon={<MenuBookIcon color="primary" />}
        >
          <PageSettings 
            pageMode={settings.pageMode}
            showPages={settings.showPages}
            onPageModeChange={handlePageModeChange}
            onShowPagesChange={handleShowPagesChange}
          />
        </SettingsSection>

        {/* Import/Export Buttons - Always visible */}
        <Stack spacing={1} sx={{ mt: 3 }}>
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              startIcon={<UploadIcon />}
              onClick={importSettings}
              sx={{ flex: 1 }}
            >
              Import
            </Button>
            <Button
              variant="outlined"
              startIcon={<DownloadIcon />}
              onClick={exportSettings}
              sx={{ flex: 1 }}
            >
              Export
            </Button>
          </Stack>
          {/* Reset Button */}
          <Button
            variant="contained"
            color="secondary"
            fullWidth
            onClick={handleResetClick}
          >
            Reset to Defaults
          </Button>
        </Stack>
      </Drawer>

      {/* Reset Confirmation Dialog */}
      <Dialog
        open={resetConfirmOpen}
        onClose={handleResetCancel}
        aria-labelledby="reset-dialog-title"
        aria-describedby="reset-dialog-description"
      >
        <DialogTitle id="reset-dialog-title">
          Reset Settings to Defaults?
        </DialogTitle>
        <DialogContent>
          <DialogContentText id="reset-dialog-description">
            This will reset all reader settings to their default values. This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleResetCancel} color="primary">
            Cancel
          </Button>
          <Button onClick={resetDefaults} color="secondary" variant="contained">
            Reset
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default ReaderSettings;
