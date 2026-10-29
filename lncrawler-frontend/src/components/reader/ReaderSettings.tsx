import {
  Drawer, Box, Typography, IconButton, Divider, Button,
  useTheme, useMediaQuery, Stack, Dialog, DialogTitle, 
  DialogContent, DialogContentText, DialogActions,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { setCookie } from '@utils/cookies';
import CloseIcon from '@mui/icons-material/Close';
import DownloadIcon from '@mui/icons-material/Download';
import UploadIcon from '@mui/icons-material/Upload';
import TextFieldsIcon from '@mui/icons-material/TextFields';
import PaletteIcon from '@mui/icons-material/Palette';
import ViewColumnIcon from '@mui/icons-material/ViewColumn';
import TouchAppIcon from '@mui/icons-material/TouchApp';
import KeyboardIcon from '@mui/icons-material/Keyboard';
import SettingsIcon from '@mui/icons-material/Settings';
import RecordVoiceOverIcon from '@mui/icons-material/RecordVoiceOver';

// Import our new components
import FontSettings from './settings/FontSettings';
import ColorSettings from './settings/ColorSettings';
import LayoutSettings from './settings/LayoutSettings';
import BehaviorSettings from './settings/BehaviorSettings';
import GestureSettings from './settings/GestureSettings';
import KeyboardSettings from './settings/KeyboardSettings';
import ReaderNavigation from './controls/ReaderNavigation';
import SettingsSection from './SettingsSection';
import { defaultSettings } from './readerDefaults';
import TtsSettings from './settings/TtsSettings';
import { TTS_NUMERIC_RANGES, TTS_ENUM_VALUES, TTS_RECORD_KEYS, isValidTtsPref, type TtsPrefs } from './tts/ttsTypes';
import { availableLanguages } from '@utils/Misc';
import { useNotification } from '@context/NotificationContext';
import { READER_COOKIE_PREFIX, READER_COOKIE_DAYS } from '@utils/storage';

const TTS_SECTION_ID = 'reader-settings-tts';

export type EdgeTapBehavior = 'none' | 'scrollUp' | 'scrollDown' | 'chapter';
export type MarkReadBehavior = 'none' | 'button' | 'automatic' | 'buttonAutomatic';
export type SwipeGesture = 'none' | 'prevChapter' | 'nextChapter';
export type KeyAction = 'none' | 'scrollUp' | 'scrollDown' | 'prevChapter' | 'nextChapter';

export interface ReaderSettings extends TtsPrefs {
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
  keyArrowLeft: KeyAction;
  keyArrowRight: KeyAction;
  keyArrowUp: KeyAction;
  keyArrowDown: KeyAction;
  keyPageUp: KeyAction;
  keyPageDown: KeyAction;
  keySpace: KeyAction;
  swipeLeftGesture: SwipeGesture;
  swipeRightGesture: SwipeGesture;
  hideScrollbar: boolean;
  paragraphIndent: boolean;
  paragraphSpacing: number;
  centerTapToOpenSettings: boolean;
  nightMode: boolean;
  nightModeStrength: number;
  nightModeScheduleEnabled: boolean;
  nightModeStartTime: string;
  nightModeEndTime: string;
}

const NUMERIC_RANGES: Partial<Record<keyof ReaderSettings, [number, number]>> = {
  ...(TTS_NUMERIC_RANGES as Partial<Record<keyof ReaderSettings, [number, number]>>),
  fontSize: [12, 32],
  margin: [-2, 22],
  lineSpacing: [1, 3],
  wordSpacing: [-2, 10],
  letterSpacing: [-1, 5],
  paragraphSpacing: [1, 3],
  dimLevel: [0, 90],
  nightModeStrength: [10, 90],
};

const KEY_ACTIONS: readonly KeyAction[] = ['none', 'scrollUp', 'scrollDown', 'prevChapter', 'nextChapter'];

const ENUM_VALUES: Partial<Record<keyof ReaderSettings, readonly string[]>> = {
  ...(TTS_ENUM_VALUES as Partial<Record<keyof ReaderSettings, readonly string[]>>),
  textAlign: ['left', 'center', 'justify', 'right'],
  leftEdgeTapBehavior: ['none', 'scrollUp', 'scrollDown', 'chapter'],
  rightEdgeTapBehavior: ['none', 'scrollUp', 'scrollDown', 'chapter'],
  markReadBehavior: ['none', 'button', 'automatic', 'buttonAutomatic'],
  swipeLeftGesture: ['none', 'prevChapter', 'nextChapter'],
  swipeRightGesture: ['none', 'prevChapter', 'nextChapter'],
  keyArrowLeft: KEY_ACTIONS,
  keyArrowRight: KEY_ACTIONS,
  keyArrowUp: KEY_ACTIONS,
  keyArrowDown: KEY_ACTIONS,
  keyPageUp: KEY_ACTIONS,
  keyPageDown: KEY_ACTIONS,
  keySpace: KEY_ACTIONS,
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
  novelLanguage: string;
  onTtsBeforePreview?: () => void;
  focusTts?: boolean;
  hasNarration?: boolean;
}

const ReaderSettings = ({
  open,
  onClose,
  settings,
  onSettingChange,
  chapterInfo,
  onNavigate,
  isAuthenticated = false,
  novelLanguage,
  onTtsBeforePreview,
  focusTts = false,
  hasNarration = false,
}: ReaderSettingsProps) => {
  const { t } = useTranslation();
  const { notify } = useNotification();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);

  // Opened from the TTS player: bring its section into view.
  useEffect(() => {
    if (!open || !focusTts) return;
    const id = window.setTimeout(() => {
      document.getElementById(TTS_SECTION_ID)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 300);
    return () => window.clearTimeout(id);
  }, [open, focusTts]);

  // Helper function to save setting to cookie
  const saveSetting = (key: string, value: unknown) => {
    setCookie(READER_COOKIE_PREFIX + key, JSON.stringify(value), READER_COOKIE_DAYS);
  };

  // Update one setting in the parent state and persist it to a cookie
  const updateSetting = <K extends keyof ReaderSettings>(key: K, value: ReaderSettings[K]) => {
    onSettingChange({ ...settings, [key]: value });
    saveSetting(key, value);
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
          
          // Validate/coerce each known key against the default's type and range
          const importedSettings: Partial<ReaderSettings> = {};
          const setImported = <K extends keyof ReaderSettings>(key: K, value: ReaderSettings[K]) => {
            importedSettings[key] = value;
          };
          
          (Object.keys(defaultSettings) as (keyof ReaderSettings)[]).forEach(key => {
            if (!(key in importedData)) return;
            const value = importedData[key];
            const def = defaultSettings[key];

            if ((TTS_RECORD_KEYS as readonly string[]).includes(key)) {
              if (value === null || typeof value !== 'object' || Array.isArray(value)) return;
              const cleaned: Record<string, string> = {};
              Object.entries(value as Record<string, unknown>).forEach(([lang, voice]) => {
                if (availableLanguages.includes(lang) && typeof voice === 'string' && voice.length <= 300) {
                  cleaned[lang] = voice;
                }
              });
              setImported(key, cleaned as never);
              return;
            }

            if (def === null) {
              if (typeof value === 'string' || value === null) setImported(key, value);
              return;
            }
            if (typeof def === 'boolean') {
              if (typeof value === 'boolean') setImported(key, value);
              return;
            }
            if (typeof def === 'number') {
              const num = typeof value === 'number' ? value : Number(value);
              const range = NUMERIC_RANGES[key];
              if (Number.isFinite(num) && (!range || (num >= range[0] && num <= range[1])) && isValidTtsPref(key, num)) {
                setImported(key, num);
              }
              return;
            }
            if (typeof def === 'string') {
              if (typeof value !== 'string') return;
              const allowed = ENUM_VALUES[key];
              if (allowed) {
                if (allowed.includes(value)) setImported(key, value);
              } else if (key === 'nightModeStartTime' || key === 'nightModeEndTime') {
                if (/^\d{2}:\d{2}$/.test(value)) setImported(key, value);
              } else if (key === 'ttsLanguage') {
                if (value === '' || availableLanguages.includes(value)) setImported(key, value);
              }
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
          notify({ message: t('readerSettings.importFailed'), severity: 'error' });
        }
      };
      
      reader.readAsText(file);
    };
    
    input.click();
  };

  return (
    <>
      <Drawer 
        className="reader-settings-drawer"
        anchor={isMobile ? "bottom" : "right"} 
        open={open} 
        onClose={onClose}
        slotProps={{
          paper: {
            sx: {
              width: isMobile ? '100%' : '350px',
              height: isMobile ? '88dvh' : undefined,
              maxHeight: isMobile ? '88vh' : '100%',
              borderTopLeftRadius: isMobile ? '16px' : 0,
              borderTopRightRadius: isMobile ? '16px' : 0,
              padding: 2,
              paddingRight: 3,
              overflow: 'auto',
              zIndex: theme.zIndex.drawer,
              boxShadow: 3,
              backgroundColor: theme.palette.background.default,
            }
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
          <Typography variant="h6">{t('readerSettings.heading')}</Typography>
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
        />

        <Divider sx={{ mb: 2 }} />

        {/* Font Settings */}
        <SettingsSection 
          title={t('readerSettings.font')} 
          icon={<TextFieldsIcon color="primary" />}
          defaultExpanded={!focusTts}
        >
          <FontSettings 
            fontSize={settings.fontSize}
            fontFamily={settings.fontFamily}
            textAlign={settings.textAlign}
            onFontSizeChange={(value) => updateSetting('fontSize', value)}
            onFontFamilyChange={(value) => updateSetting('fontFamily', value)}
            onTextAlignChange={(value) => updateSetting('textAlign', value)}
          />
        </SettingsSection>

        {/* Color Settings */}
        <SettingsSection 
          title={t('readerSettings.colors')} 
          icon={<PaletteIcon color="primary" />}
        >
          <ColorSettings 
            fontColor={settings.fontColor}
            backgroundColor={settings.backgroundColor}
            dimLevel={settings.dimLevel}
            nightMode={settings.nightMode}
            nightModeStrength={settings.nightModeStrength}
            nightModeScheduleEnabled={settings.nightModeScheduleEnabled}
            nightModeStartTime={settings.nightModeStartTime}
            nightModeEndTime={settings.nightModeEndTime}
            onFontColorChange={(color) => updateSetting('fontColor', color)}
            onBackgroundColorChange={(color) => updateSetting('backgroundColor', color)}
            onDimLevelChange={(level) => updateSetting('dimLevel', level)}
            onNightModeChange={(enabled) => updateSetting('nightMode', enabled)}
            onNightModeStrengthChange={(strength) => updateSetting('nightModeStrength', strength)}
            onNightModeScheduleChange={(enabled) => updateSetting('nightModeScheduleEnabled', enabled)}
            onNightModeStartTimeChange={(time) => updateSetting('nightModeStartTime', time)}
            onNightModeEndTimeChange={(time) => updateSetting('nightModeEndTime', time)}
          />
        </SettingsSection>

        {/* Layout Settings */}
        <SettingsSection 
          title={t('readerSettings.layout')} 
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
            onMarginChange={(margin) => updateSetting('margin', margin)}
            onLineSpacingChange={(lineSpacing) => updateSetting('lineSpacing', lineSpacing)}
            onWordSpacingChange={(spacing) => updateSetting('wordSpacing', spacing)}
            onLetterSpacingChange={(spacing) => updateSetting('letterSpacing', spacing)}
            onHideScrollbarChange={(hide) => updateSetting('hideScrollbar', hide)}
            onParagraphIndentChange={(indent) => updateSetting('paragraphIndent', indent)}
            onParagraphSpacingChange={(spacing) => updateSetting('paragraphSpacing', spacing)}
          />
        </SettingsSection>

        {/* Gesture Settings */}
        <SettingsSection 
          title={t('readerSettings.gestures')} 
          icon={<TouchAppIcon color="primary" />}
        >
          <GestureSettings
            swipeLeftGesture={settings.swipeLeftGesture}
            swipeRightGesture={settings.swipeRightGesture}
            leftEdgeTapBehavior={settings.leftEdgeTapBehavior}
            rightEdgeTapBehavior={settings.rightEdgeTapBehavior}
            centerTapToOpenSettings={settings.centerTapToOpenSettings}
            onSwipeGestureChange={(direction, gesture) => updateSetting(direction === 'left' ? 'swipeLeftGesture' : 'swipeRightGesture', gesture)}
            onEdgeTapChange={(edge, behavior) => updateSetting(edge === 'left' ? 'leftEdgeTapBehavior' : 'rightEdgeTapBehavior', behavior)}
            onCenterTapToOpenSettingsChange={(enabled) => updateSetting('centerTapToOpenSettings', enabled)}
          />
        </SettingsSection>

        {/* Keyboard Settings */}
        <SettingsSection
          title={t('readerSettings.keyboard')}
          icon={<KeyboardIcon color="primary" />}
        >
          <KeyboardSettings
            keyboardNavigation={settings.keyboardNavigation}
            keyBindings={settings}
            onKeyboardNavigationChange={(enabled) => updateSetting('keyboardNavigation', enabled)}
            onKeyActionChange={(key, action) => updateSetting(key, action)}
          />
        </SettingsSection>

        {/* Behavior Settings */}
        <SettingsSection
          title={t('readerSettings.behavior')}
          icon={<SettingsIcon color="primary" />}
        >
          <BehaviorSettings
            textSelectable={settings.textSelectable}
            savePosition={settings.savePosition}
            markReadBehavior={settings.markReadBehavior}
            onTextSelectableChange={(selectable) => updateSetting('textSelectable', selectable)}
            onSavePositionChange={(save) => updateSetting('savePosition', save)}
            onMarkReadBehaviorChange={(behavior) => updateSetting('markReadBehavior', behavior)}
            isAuthenticated={isAuthenticated}
          />
        </SettingsSection>

        {/* Text-to-speech Settings */}
        <SettingsSection
          id={TTS_SECTION_ID}
          title={t('readerSettings.tts')}
          icon={<RecordVoiceOverIcon color="primary" />}
          defaultExpanded={focusTts}
        >
          <TtsSettings
            prefs={settings}
            onChange={<K extends keyof TtsPrefs>(key: K, value: TtsPrefs[K]) =>
              updateSetting(key, value as ReaderSettings[K])}
            novelLanguage={novelLanguage}
            onBeforePreview={onTtsBeforePreview}
            hasNarration={hasNarration}
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
              {t('readerSettings.import')}
            </Button>
            <Button
              variant="outlined"
              startIcon={<DownloadIcon />}
              onClick={exportSettings}
              sx={{ flex: 1 }}
            >
              {t('readerSettings.export')}
            </Button>
          </Stack>
          {/* Reset Button */}
          <Button
            variant="contained"
            color="secondary"
            fullWidth
            onClick={handleResetClick}
          >
            {t('readerSettings.resetDefaults')}
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
          {t('readerSettings.resetTitle')}
        </DialogTitle>
        <DialogContent>
          <DialogContentText id="reset-dialog-description">
            {t('readerSettings.resetBody')}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleResetCancel} color="primary">
            {t('common.cancel')}
          </Button>
          <Button onClick={resetDefaults} color="secondary" variant="contained">
            {t('readerSettings.reset')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default ReaderSettings;
