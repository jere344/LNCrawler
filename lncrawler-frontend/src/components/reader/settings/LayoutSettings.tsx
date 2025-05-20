import React from 'react';
import {
  Box,
  Typography,
  Slider,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  SelectChangeEvent,
} from '@mui/material';

interface LayoutSettingsProps {
  margin: number;
  lineSpacing: number;
  readingMode: string;
  onMarginChange: (margin: number) => void;
  onLineSpacingChange: (spacing: number) => void;
  onReadingModeChange: (mode: string) => void;
}

// Reading mode options
export const readingModeOptions = [
  { name: 'Classic', value: 'classic' },
  { name: 'Manga', value: 'manga' },
  { name: 'Manga Reversed', value: 'mangaReversed' },
  { name: 'Webtoon', value: 'webtoon' },
];

/**
 * Component for layout-related reader settings
 */
const LayoutSettings: React.FC<LayoutSettingsProps> = ({
  margin,
  lineSpacing,
  readingMode,
  onMarginChange,
  onLineSpacingChange,
  onReadingModeChange,
}) => {
  const handleMarginChange = (_event: Event, newValue: number | number[]) => {
    onMarginChange(newValue as number);
  };

  const handleLineSpacingChange = (_event: Event, newValue: number | number[]) => {
    onLineSpacingChange(newValue as number);
  };

  const handleReadingModeChange = (event: SelectChangeEvent) => {
    onReadingModeChange(event.target.value);
  };

  return (
    <>
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>Margin: {margin}%</Typography>
        <Slider
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
        <Slider
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
        <FormControl fullWidth variant="outlined" size="small">
          <InputLabel>Reading Mode</InputLabel>
          <Select
            value={readingMode}
            onChange={handleReadingModeChange}
            label="Reading Mode"
          >
            {readingModeOptions.map((mode) => (
              <MenuItem key={mode.value} value={mode.value}>
                {mode.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>
    </>
  );
};

export default LayoutSettings;
