import React from 'react';
import {
  Box,
  Typography,
  Slider,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  ToggleButtonGroup,
  ToggleButton,
  SelectChangeEvent,
} from '@mui/material';
import FormatAlignLeftIcon from '@mui/icons-material/FormatAlignLeft';
import FormatAlignCenterIcon from '@mui/icons-material/FormatAlignCenter';
import FormatAlignJustifyIcon from '@mui/icons-material/FormatAlignJustify';
import FormatAlignRightIcon from '@mui/icons-material/ArrowForward';

interface FontSettingsProps {
  fontSize: number;
  fontFamily: string | null;
  textAlign: 'left' | 'center' | 'justify' | 'right';
  onFontSizeChange: (value: number) => void;
  onFontFamilyChange: (value: string | null) => void;
  onTextAlignChange: (value: 'left' | 'center' | 'justify' | 'right') => void;
}

// Font options
export const fontOptions = [
  { name: 'Default (theme font)', value: null },
  { name: 'Arial', value: 'Arial, sans-serif' },
  { name: 'Times New Roman', value: 'Times New Roman, serif' },
  { name: 'Georgia', value: 'Georgia, serif' },
  { name: 'Verdana', value: 'Verdana, sans-serif' },
  { name: 'OpenDyslexic', value: 'OpenDyslexic, cursive' },
  { name: 'Roboto', value: 'Roboto, sans-serif' },
];

/**
 * Component for font-related reader settings
 */
const FontSettings: React.FC<FontSettingsProps> = ({
  fontSize,
  fontFamily,
  textAlign,
  onFontSizeChange,
  onFontFamilyChange,
  onTextAlignChange,
}) => {
  const handleFontSizeChange = (_event: Event, newValue: number | number[]) => {
    onFontSizeChange(newValue as number);
  };

  const handleFontFamilyChange = (event: SelectChangeEvent) => {
    const value = event.target.value === "null" ? null : event.target.value;
    onFontFamilyChange(value);
  };

  const handleTextAlignChange = (_event: React.MouseEvent<HTMLElement>, newValue: string | null) => {
    if (newValue !== null) {
      onTextAlignChange(newValue as 'left' | 'center' | 'justify' | 'right');
    }
  };

  return (
    <>
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>Font Size: {fontSize}px</Typography>
        <Slider
          value={fontSize}
          onChange={handleFontSizeChange}
          min={12}
          max={32}
          step={1}
          marks={[
            { value: 12.5, label: '12px' },
            { value: 22, label: '22px' },
            { value: 31.5, label: '32px' },
          ]}
          valueLabelDisplay="auto"
        />
      </Box>

      <Box sx={{ mb: 2 }}>
        <FormControl fullWidth variant="outlined" size="small">
          <InputLabel>Font</InputLabel>
          <Select
            value={fontFamily === null ? "null" : fontFamily}
            onChange={handleFontFamilyChange}
            label="Font"
          >
            {fontOptions.map((font) => (
              <MenuItem 
                key={font.name} 
                value={font.value === null ? "null" : font.value}
                style={{ fontFamily: font.value || undefined }}
              >
                {font.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>

      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>Text Alignment</Typography>
        <ToggleButtonGroup
          value={textAlign}
          exclusive
          onChange={handleTextAlignChange}
          aria-label="text alignment"
          fullWidth
          size="small"
        >
          <ToggleButton value="left" aria-label="left aligned">
            <FormatAlignLeftIcon />
          </ToggleButton>
          <ToggleButton value="center" aria-label="centered">
            <FormatAlignCenterIcon />
          </ToggleButton>
          <ToggleButton value="justify" aria-label="justified">
            <FormatAlignJustifyIcon />
          </ToggleButton>
          <ToggleButton value="right" aria-label="right aligned">
            <FormatAlignRightIcon />
          </ToggleButton>
        </ToggleButtonGroup>
      </Box>
    </>
  );
};

export default FontSettings;
