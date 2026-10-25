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
import { useTranslation } from 'react-i18next';
import { MarkReadBehavior } from '../ReaderSettings';

interface BehaviorSettingsProps {
  textSelectable: boolean;
  savePosition: boolean;
  markReadBehavior: MarkReadBehavior;
  onTextSelectableChange: (selectable: boolean) => void;
  onSavePositionChange: (save: boolean) => void;
  onMarkReadBehaviorChange: (behavior: MarkReadBehavior) => void;
  isAuthenticated?: boolean;
}

/**
 * Component for behavior-related reader settings
 */
const BehaviorSettings: React.FC<BehaviorSettingsProps> = ({
  textSelectable,
  savePosition,
  markReadBehavior,
  onTextSelectableChange,
  onSavePositionChange,
  onMarkReadBehaviorChange,
  isAuthenticated = false,
}) => {
  const { t } = useTranslation();

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
    </Box>
  );
};

export default BehaviorSettings;
