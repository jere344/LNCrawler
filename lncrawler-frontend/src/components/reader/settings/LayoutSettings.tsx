import React from 'react';
import {
  Box,
  Typography,
  FormControlLabel,
  Switch,
} from '@mui/material';
import MobileSafeSlider from '../../common/MobileSafeSlider';

interface LayoutSettingsProps {
  margin: number;
  lineSpacing: number;
  hideScrollbar: boolean;
  onMarginChange: (margin: number) => void;
  onLineSpacingChange: (spacing: number) => void;
  onHideScrollbarChange: (hide: boolean) => void;
}


/**
 * Component for layout-related reader settings
 */
const LayoutSettings: React.FC<LayoutSettingsProps> = ({
  margin,
  lineSpacing,
  hideScrollbar,
  onMarginChange,
  onLineSpacingChange,
  onHideScrollbarChange,
}) => {
  const handleMarginChange = (_event: Event, newValue: number | number[]) => {
    onMarginChange(newValue as number);
  };

  const handleLineSpacingChange = (_event: Event, newValue: number | number[]) => {
    onLineSpacingChange(newValue as number);
  };

  const handleHideScrollbarChange = (_event: React.ChangeEvent<HTMLInputElement>, checked: boolean) => {
    onHideScrollbarChange(checked);
  };

  return (
    <>
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>Margin: {margin}%</Typography>
        <MobileSafeSlider
          value={margin}
          onChange={handleMarginChange}
          min={-2}
          max={22}
          step={1}
          marks={[
            { value: -1.5, label: '-2%' },
            { value: 10, label: '10%' },
            { value: 21.5, label: '22%' },
          ]}
          valueLabelDisplay="auto"
        />
      </Box>

      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>Line Spacing: {lineSpacing}</Typography>
        <MobileSafeSlider
          value={lineSpacing}
          onChange={handleLineSpacingChange}
          min={1}
          max={3}
          step={0.1}
          marks={[
            { value: 1.02, label: '1x' },
            { value: 2, label: '2x' },
            { value: 2.98, label: '3x' },
          ]}
          valueLabelDisplay="auto"
        />
      </Box>

      <Box sx={{ mb: 2 }}>
        <FormControlLabel
          control={
            <Switch
              checked={hideScrollbar}
              onChange={handleHideScrollbarChange}
              color="primary"
            />
          }
          label="Hide Scrollbar"
        />
        <Typography variant="caption" color="text.secondary" display="block">
          Hide browser scrollbar for a cleaner reading experience
        </Typography>
      </Box>
    </>
  );
};

export default LayoutSettings;
