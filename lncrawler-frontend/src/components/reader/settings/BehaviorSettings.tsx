import React from 'react';
import {
  Box,
  Typography,
  FormControl,
  Select,
  MenuItem,
  FormControlLabel,
  Switch,
  Grid2 as Grid,
  SelectChangeEvent,
  FormHelperText,
} from '@mui/material';
import BlockIcon from '@mui/icons-material/Block';
import VerticalAlignTopIcon from '@mui/icons-material/VerticalAlignTop';
import VerticalAlignBottomIcon from '@mui/icons-material/VerticalAlignBottom';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { EdgeTapBehavior, MarkReadBehavior } from '../ReaderSettings';

interface BehaviorSettingsProps {
  leftEdgeTapBehavior: EdgeTapBehavior;
  rightEdgeTapBehavior: EdgeTapBehavior;
  textSelectable: boolean;
  savePosition: boolean;
  markReadBehavior: MarkReadBehavior;
  keyboardNavigation: boolean;
  onEdgeTapChange: (edge: 'left' | 'right', behavior: EdgeTapBehavior) => void;
  onTextSelectableChange: (selectable: boolean) => void;
  onSavePositionChange: (save: boolean) => void;
  onMarkReadBehaviorChange: (behavior: MarkReadBehavior) => void;
  onKeyboardNavigationChange: (enabled: boolean) => void;
  isAuthenticated?: boolean;
}

// Edge tap options
export const edgeTapOptions = [
  { name: 'Do Nothing', value: 'none', icon: BlockIcon },
  { name: 'Scroll Up', value: 'scrollUp', icon: VerticalAlignTopIcon },
  { name: 'Scroll Down', value: 'scrollDown', icon: VerticalAlignBottomIcon },
  { name: 'Change Chapter', value: 'chapter', icon: ChevronRightIcon },
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
  onEdgeTapChange,
  onTextSelectableChange,
  onSavePositionChange,
  onMarkReadBehaviorChange,
  onKeyboardNavigationChange,
  isAuthenticated = false,
}) => {
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

  const handleKeyboardNavigationChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onKeyboardNavigationChange(event.target.checked);
  };

  const getMarkReadExplanation = (behavior: MarkReadBehavior) => {
    switch (behavior) {
      case 'none':
        return 'Mark as read buttons will be hidden.';
      case 'button':
        return 'Mark as read buttons will be shown but chapters won\'t be marked automatically.';
      case 'automatic':
        return 'Previous chapter will be automatically marked as read when navigating to a new chapter.';
      case 'buttonAutomatic':
        return 'Both manual marking via buttons and automatic marking when changing chapters are enabled.';
      default:
        return '';
    }
  };

  return (
    <Box>
      <Typography variant="subtitle1" sx={{ mb: 2 }}>Behavior Settings</Typography>
      
      {/* Edge Tap Settings */}
      <Typography variant="body2" sx={{ mt: 2, mb: 1 }}>Left Edge Tap (Mobile)</Typography>
      <FormControl fullWidth size="small" sx={{ mb: 2 }}>
        <Select
          value={leftEdgeTapBehavior}
          onChange={handleEdgeTapChange('left')}
        >
          {edgeTapOptions.map((option) => (
            <MenuItem key={`left-${option.value}`} value={option.value}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                {React.createElement(option.icon, { sx: { mr: 1, fontSize: '1.2rem' } })}
                {option.name}
              </Box>
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <Typography variant="body2" sx={{ mt: 2, mb: 1 }}>Right Edge Tap (Mobile)</Typography>
      <FormControl fullWidth size="small" sx={{ mb: 2 }}>
        <Select
          value={rightEdgeTapBehavior}
          onChange={handleEdgeTapChange('right')}
        >
          {edgeTapOptions.map((option) => (
            <MenuItem key={`right-${option.value}`} value={option.value}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                {React.createElement(option.icon, { sx: { mr: 1, fontSize: '1.2rem' } })}
                {option.name}
              </Box>
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      {/* Mark as Read Behavior (only for authenticated users) */}
      {isAuthenticated && (
        <>
          <Typography variant="body2" sx={{ mt: 2, mb: 1 }}>Mark as Read Behavior</Typography>
          <FormControl fullWidth size="small" sx={{ mb: 1 }}>
            <Select
              value={markReadBehavior}
              onChange={handleMarkReadBehaviorChange}
            >
              <MenuItem value="none">None</MenuItem>
              <MenuItem value="button">Button Only</MenuItem>
              <MenuItem value="automatic">Automatic</MenuItem>
              <MenuItem value="buttonAutomatic">Button + Automatic</MenuItem>
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
        label="Allow Text Selection/Copy"
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
        label="Remember Reading Position"
        sx={{ mb: 1, display: 'block' }}
      />
      
      <FormControlLabel
        control={
          <Switch
            checked={keyboardNavigation}
            onChange={handleKeyboardNavigationChange}
            color="primary"
          />
        }
        label="Enable Keyboard Navigation (←/→ arrows)"
        sx={{ mb: 1, display: 'block' }}
      />
    </Box>
  );
};

export default BehaviorSettings;
