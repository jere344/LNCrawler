import React from 'react';
import {
  Box,
  Typography,
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
import { useTranslation } from 'react-i18next';
import MobileSafeSlider from '../../common/MobileSafeSlider';

interface FontSettingsProps {
  fontSize: number;
  fontFamily: string | null;
  textAlign: 'left' | 'center' | 'justify' | 'right';
  onFontSizeChange: (value: number) => void;
  onFontFamilyChange: (value: string | null) => void;
  onTextAlignChange: (value: 'left' | 'center' | 'justify' | 'right') => void;
}

// Font options
const fontOptions = [
  { labelKey: 'fontSettings.defaultThemeFont', value: null },
  { labelKey: 'fontSettings.arial', value: 'Arial, sans-serif' },
  { labelKey: 'fontSettings.timesNewRoman', value: 'Times New Roman, serif' },
  { labelKey: 'fontSettings.georgia', value: 'Georgia, serif' },
  { labelKey: 'fontSettings.verdana', value: 'Verdana, sans-serif' },
  { labelKey: 'fontSettings.openDyslexic', value: 'OpenDyslexic, cursive' },
  { labelKey: 'fontSettings.roboto', value: 'Roboto, sans-serif' },
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
  const { t } = useTranslation();

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
        <Typography variant="subtitle1" gutterBottom>{t('fontSettings.fontSize', { size: fontSize })}</Typography>
        <MobileSafeSlider
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
          <InputLabel>{t('fontSettings.font')}</InputLabel>
          <Select
            value={fontFamily === null ? "null" : fontFamily}
            onChange={handleFontFamilyChange}
            label={t('fontSettings.font')}
          >
            {fontOptions.map((font) => (
              <MenuItem 
                key={font.labelKey} 
                value={font.value === null ? "null" : font.value}
                style={{ fontFamily: font.value || undefined }}
              >
                {t(font.labelKey)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>

      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>{t('fontSettings.textAlignment')}</Typography>
        <ToggleButtonGroup
          value={textAlign}
          exclusive
          onChange={handleTextAlignChange}
          aria-label={t('fontSettings.textAlignment')}
          fullWidth
          size="small"
        >
          <ToggleButton value="left" aria-label={t('fontSettings.alignLeft')}>
            <FormatAlignLeftIcon />
          </ToggleButton>
          <ToggleButton value="center" aria-label={t('fontSettings.alignCenter')}>
            <FormatAlignCenterIcon />
          </ToggleButton>
          <ToggleButton value="justify" aria-label={t('fontSettings.alignJustify')}>
            <FormatAlignJustifyIcon />
          </ToggleButton>
          <ToggleButton value="right" aria-label={t('fontSettings.alignRight')}>
            <FormatAlignRightIcon />
          </ToggleButton>
        </ToggleButtonGroup>
      </Box>
    </>
  );
};

export default FontSettings;
