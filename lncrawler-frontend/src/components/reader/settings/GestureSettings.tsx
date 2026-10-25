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
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { useTranslation } from 'react-i18next';
import { EdgeTapBehavior, SwipeGesture } from '../ReaderSettings';

interface GestureSettingsProps {
  swipeLeftGesture: SwipeGesture;
  swipeRightGesture: SwipeGesture;
  leftEdgeTapBehavior: EdgeTapBehavior;
  rightEdgeTapBehavior: EdgeTapBehavior;
  centerTapToOpenSettings: boolean;
  onSwipeGestureChange: (direction: 'left' | 'right', gesture: SwipeGesture) => void;
  onEdgeTapChange: (edge: 'left' | 'right', behavior: EdgeTapBehavior) => void;
  onCenterTapToOpenSettingsChange: (enabled: boolean) => void;
}

// Swipe gesture options
const swipeGestureOptions = [
  { labelKey: 'gestureSettings.doNothing', value: 'none', icon: BlockIcon },
  { labelKey: 'gestureSettings.previousChapter', value: 'prevChapter', icon: KeyboardArrowLeftIcon },
  { labelKey: 'gestureSettings.nextChapter', value: 'nextChapter', icon: KeyboardArrowRightIcon },
];

// Edge tap options
const edgeTapOptions = [
  { labelKey: 'behaviorSettings.doNothing', value: 'none', icon: BlockIcon },
  { labelKey: 'behaviorSettings.scrollUp', value: 'scrollUp', icon: VerticalAlignTopIcon },
  { labelKey: 'behaviorSettings.scrollDown', value: 'scrollDown', icon: VerticalAlignBottomIcon },
  { labelKey: 'behaviorSettings.changeChapter', value: 'chapter', icon: ChevronRightIcon },
];

/**
 * Component for gesture-related reader settings
 */
const GestureSettings: React.FC<GestureSettingsProps> = ({
  swipeLeftGesture,
  swipeRightGesture,
  leftEdgeTapBehavior,
  rightEdgeTapBehavior,
  centerTapToOpenSettings,
  onSwipeGestureChange,
  onEdgeTapChange,
  onCenterTapToOpenSettingsChange,
}) => {
  const { t } = useTranslation();

  const handleSwipeGestureChange = (direction: 'left' | 'right') => (event: SelectChangeEvent) => {
    onSwipeGestureChange(direction, event.target.value as SwipeGesture);
  };

  const handleEdgeTapChange = (edge: 'left' | 'right') => (event: SelectChangeEvent) => {
    onEdgeTapChange(edge, event.target.value as EdgeTapBehavior);
  };

  return (
    <Box>
      <Typography variant="subtitle1" sx={{ mb: 2 }}>{t('gestureSettings.heading')}</Typography>
      
      {/* Swipe Left Settings */}
      <Typography variant="body2" sx={{ mt: 2, mb: 1 }}>{t('gestureSettings.swipeLeft')}</Typography>
      <FormControl fullWidth size="small" sx={{ mb: 1 }}>
        <Select
          value={swipeLeftGesture}
          onChange={handleSwipeGestureChange('left')}
        >
          {swipeGestureOptions.map((option) => (
            <MenuItem key={`swipe-left-${option.value}`} value={option.value}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                {React.createElement(option.icon, { sx: { mr: 1, fontSize: '1.2rem' } })}
                {t(option.labelKey)}
              </Box>
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      {/* Swipe Right Settings */}
      <Typography variant="body2" sx={{ mt: 2, mb: 1 }}>{t('gestureSettings.swipeRight')}</Typography>
      <FormControl fullWidth size="small" sx={{ mb: 1 }}>
        <Select
          value={swipeRightGesture}
          onChange={handleSwipeGestureChange('right')}
        >
          {swipeGestureOptions.map((option) => (
            <MenuItem key={`swipe-right-${option.value}`} value={option.value}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                {React.createElement(option.icon, { sx: { mr: 1, fontSize: '1.2rem' } })}
                {t(option.labelKey)}
              </Box>
            </MenuItem>
          ))}
        </Select>
      </FormControl>

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

export default GestureSettings;
