import React from 'react';
import {
  Box,
  Typography,
  FormControl,
  Select,
  MenuItem,
  FormControlLabel,
  Switch,
  FormHelperText,
  SelectChangeEvent,
} from '@mui/material';
import KeyboardArrowLeftIcon from '@mui/icons-material/KeyboardArrowLeft';
import KeyboardArrowRightIcon from '@mui/icons-material/KeyboardArrowRight';
import BlockIcon from '@mui/icons-material/Block';
import VerticalAlignTopIcon from '@mui/icons-material/VerticalAlignTop';
import VerticalAlignBottomIcon from '@mui/icons-material/VerticalAlignBottom';
import { useTranslation } from 'react-i18next';
import { KeyAction, ReaderSettings } from '../ReaderSettings';

// Settings keys holding the action bound to each key
export type KeyBindingKey = 'keyArrowLeft' | 'keyArrowRight' | 'keyArrowUp' | 'keyArrowDown' | 'keyPageUp' | 'keyPageDown' | 'keySpace';

interface KeyboardSettingsProps {
  keyboardNavigation: boolean;
  keyBindings: Pick<ReaderSettings, KeyBindingKey>;
  onKeyboardNavigationChange: (enabled: boolean) => void;
  onKeyActionChange: (settingKey: KeyBindingKey, action: KeyAction) => void;
}

// Keys in display order
const keyRows: { settingKey: KeyBindingKey; labelKey: string }[] = [
  { settingKey: 'keyArrowLeft', labelKey: 'keyboardSettings.arrowLeft' },
  { settingKey: 'keyArrowRight', labelKey: 'keyboardSettings.arrowRight' },
  { settingKey: 'keyArrowUp', labelKey: 'keyboardSettings.arrowUp' },
  { settingKey: 'keyArrowDown', labelKey: 'keyboardSettings.arrowDown' },
  { settingKey: 'keyPageUp', labelKey: 'keyboardSettings.pageUp' },
  { settingKey: 'keyPageDown', labelKey: 'keyboardSettings.pageDown' },
  { settingKey: 'keySpace', labelKey: 'keyboardSettings.space' },
];

// Key action options
const keyActionOptions = [
  { labelKey: 'keyboardSettings.doNothing', value: 'none', icon: BlockIcon },
  { labelKey: 'keyboardSettings.scrollUp', value: 'scrollUp', icon: VerticalAlignTopIcon },
  { labelKey: 'keyboardSettings.scrollDown', value: 'scrollDown', icon: VerticalAlignBottomIcon },
  { labelKey: 'keyboardSettings.previousChapter', value: 'prevChapter', icon: KeyboardArrowLeftIcon },
  { labelKey: 'keyboardSettings.nextChapter', value: 'nextChapter', icon: KeyboardArrowRightIcon },
];

/**
 * Component for keyboard-related reader settings
 */
const KeyboardSettings: React.FC<KeyboardSettingsProps> = ({
  keyboardNavigation,
  keyBindings,
  onKeyboardNavigationChange,
  onKeyActionChange,
}) => {
  const { t } = useTranslation();

  const handleKeyActionChange = (settingKey: KeyBindingKey) => (event: SelectChangeEvent) => {
    onKeyActionChange(settingKey, event.target.value as KeyAction);
  };

  return (
    <Box>
      {/* Keyboard Navigation Toggle */}
      <FormControl fullWidth sx={{ mb: 2 }}>
        <FormControlLabel
          control={
            <Switch
              checked={keyboardNavigation}
              onChange={(e) => onKeyboardNavigationChange(e.target.checked)}
            />
          }
          label={t('keyboardSettings.enable')}
        />
        <FormHelperText>{t('keyboardSettings.enableHint')}</FormHelperText>
      </FormControl>

      {/* One action per key */}
      {keyRows.map((row) => (
        <React.Fragment key={row.settingKey}>
          <Typography variant="body2" sx={{ mt: 2, mb: 1 }}>{t(row.labelKey)}</Typography>
          <FormControl fullWidth size="small" sx={{ mb: 1 }}>
            <Select
              value={keyBindings[row.settingKey]}
              disabled={!keyboardNavigation}
              onChange={handleKeyActionChange(row.settingKey)}
            >
              {keyActionOptions.map((option) => (
                <MenuItem key={`${row.settingKey}-${option.value}`} value={option.value}>
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    {React.createElement(option.icon, { sx: { mr: 1, fontSize: '1.2rem' } })}
                    {t(option.labelKey)}
                  </Box>
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </React.Fragment>
      ))}
    </Box>
  );
};

export default KeyboardSettings;
