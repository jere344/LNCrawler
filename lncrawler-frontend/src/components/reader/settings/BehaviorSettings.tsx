import React from 'react';
import {
  Box,
  Typography,
  FormControl,
  Select,
  MenuItem,
  FormControlLabel,
  Switch,
  SelectChangeEvent,
  FormHelperText,
} from '@mui/material';
import BlockIcon from '@mui/icons-material/Block';
import VerticalAlignTopIcon from '@mui/icons-material/VerticalAlignTop';
import VerticalAlignBottomIcon from '@mui/icons-material/VerticalAlignBottom';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { useTranslation } from 'react-i18next';
import { EdgeTapBehavior, MarkReadBehavior } from '../ReaderSettings';

interface BehaviorSettingsProps {
  leftEdgeTapBehavior: EdgeTapBehavior;
  rightEdgeTapBehavior: EdgeTapBehavior;
  textSelectable: boolean;
  savePosition: boolean;
  markReadBehavior: MarkReadBehavior;
  keyboardNavigation: boolean;
  centerTapToOpenSettings: boolean;
  onEdgeTapChange: (edge: 'left' | 'right', behavior: EdgeTapBehavior) => void;
  onTextSelectableChange: (selectable: boolean) => void;
  onSavePositionChange: (save: boolean) => void;
  onMarkReadBehaviorChange: (behavior: MarkReadBehavior) => void;
  onKeyboardNavigationChange: (enabled: boolean) => void;
  onCenterTapToOpenSettingsChange: (enabled: boolean) => void;
  isAuthenticated?: boolean;
}

// Edge tap options
export const edgeTapOptions = [
  { labelKey: 'behaviorSettings.doNothing', value: 'none', icon: BlockIcon },
  { labelKey: 'behaviorSettings.scrollUp', value: 'scrollUp', icon: VerticalAlignTopIcon },
  { labelKey: 'behaviorSettings.scrollDown', value: 'scrollDown', icon: VerticalAlignBottomIcon },
  { labelKey: 'behaviorSettings.changeChapter', value: 'chapter', icon: ChevronRightIcon },
];

/**
 * Component for behavior-related reader settings
 */
const BehaviorSettings: React.FC<BehaviorSettingsProps> = ({
  leftEdgeTapBehavior,
  rightEdgeTapBehavior,
  textSelectable,
  savePosition,
  markReadBehavior,
  keyboardNavigation,
  centerTapToOpenSettings,
  onEdgeTapChange,
  onTextSelectableChange,
  onSavePositionChange,
  onMarkReadBehaviorChange,
  onKeyboardNavigationChange,
  onCenterTapToOpenSettingsChange,
  isAuthenticated = false,
}) => {
  const { t } = useTranslation();

  const handleEdgeTapChange = (edge: 'left' | 'right') => (event: SelectChangeEvent) => {
    onEdgeTapChange(edge, event.target.value as EdgeTapBehavior);
  };

  const handleTextSelectableChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onTextSelectableChange(event.target.checked);
  };

  const handleSavePositionChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onSavePositionChange(event.target.checked);
  };

  const handleMarkReadBehaviorChange = (event: SelectChangeEvent<string>) => {
    onMarkReadBehaviorChange(event.target.value as MarkReadBehavior);
  };

  const getMarkReadExplanation = (behavior: MarkReadBehavior) => {
    switch (behavior) {
      case 'none':
        return t('behaviorSettings.hidden');
      case 'button':
        return t('behaviorSettings.shownNotAuto');
      case 'automatic':
        return t('behaviorSettings.autoPrev');
      case 'buttonAutomatic':
        return t('behaviorSettings.bothEnabled');
      default:
        return '';
    }
  };

  return (
    <Box>
      <Typography variant="subtitle1" sx={{ mb: 2 }}>{t('behaviorSettings.heading')}</Typography>
      
      {/* Edge Tap Settings */}
      <Typography variant="body2" sx={{ mt: 2, mb: 1 }}>{t('behaviorSettings.leftEdgeTap')}</Typography>
      <FormControl fullWidth size="small" sx={{ mb: 2 }}>
        <Select
          value={leftEdgeTapBehavior}
          onChange={handleEdgeTapChange('left')}
        >
          {edgeTapOptions.map((option) => (
            <MenuItem key={`left-${option.value}`} value={option.value}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                {React.createElement(option.icon, { sx: { mr: 1, fontSize: '1.2rem' } })}
                {t(option.labelKey)}
              </Box>
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <Typography variant="body2" sx={{ mt: 2, mb: 1 }}>{t('behaviorSettings.rightEdgeTap')}</Typography>
      <FormControl fullWidth size="small" sx={{ mb: 2 }}>
        <Select
          value={rightEdgeTapBehavior}
          onChange={handleEdgeTapChange('right')}
        >
          {edgeTapOptions.map((option) => (
            <MenuItem key={`right-${option.value}`} value={option.value}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                {React.createElement(option.icon, { sx: { mr: 1, fontSize: '1.2rem' } })}
                {t(option.labelKey)}
              </Box>
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      {/* Mark as Read Behavior (only for authenticated users) */}
      {isAuthenticated && (
        <>
          <Typography variant="body2" sx={{ mt: 2, mb: 1 }}>{t('behaviorSettings.markAsReadBehavior')}</Typography>
          <FormControl fullWidth size="small" sx={{ mb: 1 }}>
            <Select
              value={markReadBehavior}
              onChange={handleMarkReadBehaviorChange}
            >
              <MenuItem value="none">{t('behaviorSettings.none')}</MenuItem>
              <MenuItem value="button">{t('behaviorSettings.buttonOnly')}</MenuItem>
              <MenuItem value="automatic">{t('behaviorSettings.automatic')}</MenuItem>
              <MenuItem value="buttonAutomatic">{t('behaviorSettings.buttonAndAutomatic')}</MenuItem>
            </Select>
            <FormHelperText>
              {getMarkReadExplanation(markReadBehavior)}
            </FormHelperText>
          </FormControl>
        </>
      )}

      {/* Text Selection & Position */}
      <FormControlLabel
        control={
          <Switch
            checked={textSelectable}
            onChange={handleTextSelectableChange}
            color="primary"
          />
        }
        label={t('behaviorSettings.allowSelection')}
        sx={{ mt: 2, mb: 1, display: 'block' }}
      />
      
      <FormControlLabel
        control={
          <Switch
            checked={savePosition}
            onChange={handleSavePositionChange}
            color="primary"
          />
        }
        label={t('behaviorSettings.rememberPosition')}
        sx={{ mb: 1, display: 'block' }}
      />
      
      {/* Keyboard Navigation Toggle */}
      <FormControl fullWidth sx={{ mb: 2 }}>
        <FormControlLabel
          control={
            <Switch
              checked={keyboardNavigation}
              onChange={(e) => onKeyboardNavigationChange(e.target.checked)}
            />
          }
          label={t('behaviorSettings.keyboardNavigation')}
        />
        <FormHelperText>{t('behaviorSettings.keyboardHint')}</FormHelperText>
      </FormControl>

      {/* Center Tap to Open Settings Toggle */}
      <FormControl fullWidth sx={{ mb: 2 }}>
        <FormControlLabel
          control={
            <Switch
              checked={centerTapToOpenSettings}
              onChange={(e) => onCenterTapToOpenSettingsChange(e.target.checked)}
            />
          }
          label={t('behaviorSettings.centerTapSettings')}
        />
        <FormHelperText>{t('behaviorSettings.centerTapHint')}</FormHelperText>
      </FormControl>
    </Box>
  );
};

export default BehaviorSettings;
