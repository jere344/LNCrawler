import React from 'react';
import {
  Box,
  Typography,
  FormControl,
  Select,
  MenuItem,
  SelectChangeEvent,
} from '@mui/material';
import KeyboardArrowLeftIcon from '@mui/icons-material/KeyboardArrowLeft';
import KeyboardArrowRightIcon from '@mui/icons-material/KeyboardArrowRight';
import BlockIcon from '@mui/icons-material/Block';
import { useTranslation } from 'react-i18next';
import { SwipeGesture } from '../ReaderSettings';

interface GestureSettingsProps {
  swipeLeftGesture: SwipeGesture;
  swipeRightGesture: SwipeGesture;
  onSwipeGestureChange: (direction: 'left' | 'right', gesture: SwipeGesture) => void;
}

// Swipe gesture options
const swipeGestureOptions = [
  { labelKey: 'gestureSettings.doNothing', value: 'none', icon: BlockIcon },
  { labelKey: 'gestureSettings.previousChapter', value: 'prevChapter', icon: KeyboardArrowLeftIcon },
  { labelKey: 'gestureSettings.nextChapter', value: 'nextChapter', icon: KeyboardArrowRightIcon },
];

/**
 * Component for gesture-related reader settings
 */
const GestureSettings: React.FC<GestureSettingsProps> = ({
  swipeLeftGesture,
  swipeRightGesture,
  onSwipeGestureChange,
}) => {
  const { t } = useTranslation();

  const handleSwipeGestureChange = (direction: 'left' | 'right') => (event: SelectChangeEvent) => {
    onSwipeGestureChange(direction, event.target.value as SwipeGesture);
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
    </Box>
  );
};

export default GestureSettings;
