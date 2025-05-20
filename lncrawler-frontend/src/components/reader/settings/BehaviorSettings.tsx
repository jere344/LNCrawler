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
} from '@mui/material';
import BlockIcon from '@mui/icons-material/Block';
import VerticalAlignTopIcon from '@mui/icons-material/VerticalAlignTop';
import VerticalAlignBottomIcon from '@mui/icons-material/VerticalAlignBottom';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { EdgeTapBehavior } from '../ReaderSettings';

interface BehaviorSettingsProps {
  leftEdgeTapBehavior: EdgeTapBehavior;
  rightEdgeTapBehavior: EdgeTapBehavior;
  textSelectable: boolean;
  savePosition: boolean;
  onEdgeTapChange: (edge: 'left' | 'right', behavior: EdgeTapBehavior) => void;
  onTextSelectableChange: (selectable: boolean) => void;
  onSavePositionChange: (save: boolean) => void;
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
  onEdgeTapChange,
  onTextSelectableChange,
  onSavePositionChange,
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

  return (
    <>
      <Box sx={{ mb: 3 }}>
        <FormControlLabel
          control={
            <Switch
              checked={textSelectable}
              onChange={handleTextSelectableChange}
              color="primary"
            />
          }
          label="Allow Text Selection/Copy"
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
        />
      </Box>

      {/* Edge Tap Behavior */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="subtitle1" gutterBottom>Edge Tap Behavior</Typography>
        <Grid container spacing={2}>
          <Grid size={6}>
            <Typography variant="body2" color="text.secondary" align="center" gutterBottom>
              Left Edge
            </Typography>
            <FormControl fullWidth size="small">
              <Select
                value={leftEdgeTapBehavior}
                onChange={handleEdgeTapChange('left')}
                displayEmpty
                renderValue={(selected) => {
                  const option = edgeTapOptions.find(opt => opt.value === selected);
                  return (
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      {option && React.createElement(option.icon, { sx: { mr: 1, fontSize: '1.2rem' } })}
                      <Typography variant="body2" noWrap>
                        {option ? option.name : ''}
                      </Typography>
                    </Box>
                  );
                }}
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
          </Grid>
          <Grid size={6}>
            <Typography variant="body2" color="text.secondary" align="center" gutterBottom>
              Right Edge
            </Typography>
            <FormControl fullWidth size="small">
              <Select
                value={rightEdgeTapBehavior}
                onChange={handleEdgeTapChange('right')}
                displayEmpty
                renderValue={(selected) => {
                  const option = edgeTapOptions.find(opt => opt.value === selected);
                  return (
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      {option && React.createElement(option.icon, { sx: { mr: 1, fontSize: '1.2rem' } })}
                      <Typography variant="body2" noWrap>
                        {option ? option.name : ''}
                      </Typography>
                    </Box>
                  );
                }}
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
          </Grid>
        </Grid>
      </Box>
    </>
  );
};

export default BehaviorSettings;
