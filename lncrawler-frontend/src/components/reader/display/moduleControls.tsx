import type { ReactNode } from 'react';
import { Box, Button, Chip, FormControlLabel, Slider, Switch, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import FormatAlignLeftIcon from '@mui/icons-material/FormatAlignLeft';
import FormatAlignCenterIcon from '@mui/icons-material/FormatAlignCenter';
import FormatAlignJustifyIcon from '@mui/icons-material/FormatAlignJustify';
import FormatAlignRightIcon from '@mui/icons-material/FormatAlignRight';
import { useTranslation } from 'react-i18next';
import { useReaderSettings } from '../hooks/useReaderSettings';
import { updateReaderSetting } from '../readerSettingsStore';
import { type ReaderSettings } from '../readerSettingsSchema';
import { READER_THEMES, findReaderTheme, fontOptions } from '../readerOptions';
import { useSiteTheme } from '../theme/siteTheme';
import Stepper from './Stepper';
import { STEPPER_SPECS } from './stepperSpecs';

// Keeps the slider thumb from being taken over by a touch scroll
const SLIDER_SX = { '& .MuiSlider-thumb': { touchAction: 'none' } };

const ModuleRow = ({ children }: { children: ReactNode }) => (
  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>{children}</Box>
);

// A slider with its percentage readout, for the Dim and Warm modules
const LabelledSlider = ({ label, value, min, max, onChange }: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) => (
  <>
    <Slider
      aria-label={label}
      value={value}
      min={min}
      max={max}
      step={5}
      onChange={(_event, next) => onChange(next as number)}
      sx={{ flex: 1, mx: 1.5, ...SLIDER_SX }}
    />
    <Typography variant="body2" component="output" sx={{ minWidth: '3em', textAlign: 'end' }}>{value}%</Typography>
  </>
);

export const SizeModule = () => {
  const { t } = useTranslation();
  return (
    <Stepper
      settingKey="fontSize"
      {...STEPPER_SPECS.fontSize}
      label={t('readerDisplay.modules.size.label')}
      decreaseLabel={<Typography component="span" sx={{ fontSize: '0.85rem', lineHeight: 1 }}>A</Typography>}
      increaseLabel={<Typography component="span" sx={{ fontSize: '1.4rem', lineHeight: 1 }}>A</Typography>}
    />
  );
};

export const LineModule = () => {
  const { t } = useTranslation();
  return (
    <Stepper
      settingKey="lineSpacing"
      {...STEPPER_SPECS.lineSpacing}
      label={t('readerDisplay.modules.line.label')}
    />
  );
};

export const ParagraphModule = () => {
  const { t } = useTranslation();
  return (
    <Stepper
      settingKey="paragraphSpacing"
      {...STEPPER_SPECS.paragraphSpacing}
      label={t('readerDisplay.modules.para.label')}
    />
  );
};

export const MarginModule = () => {
  const { t } = useTranslation();
  return (
    <Stepper
      settingKey="margin"
      {...STEPPER_SPECS.margin}
      label={t('readerDisplay.modules.margin.label')}
    />
  );
};

export const IndentModule = () => {
  const { t } = useTranslation();
  const indent = useReaderSettings().paragraphIndent;
  return (
    <Chip
      label={t('readerDisplay.modules.indent.label')}
      clickable
      onClick={() => updateReaderSetting('paragraphIndent', !indent)}
      aria-pressed={indent}
      color={indent ? 'primary' : 'default'}
      variant={indent ? 'filled' : 'outlined'}
      sx={{ alignSelf: 'center' }}
    />
  );
};

export const AlignModule = () => {
  const { t } = useTranslation();
  const textAlign = useReaderSettings().textAlign;
  return (
    <ToggleButtonGroup
      value={textAlign}
      exclusive
      size="small"
      fullWidth
      aria-label={t('fontSettings.textAlignment')}
      onChange={(_event, value: ReaderSettings['textAlign'] | null) => {
        if (value) updateReaderSetting('textAlign', value);
      }}
    >
      <ToggleButton value="left" aria-label={t('fontSettings.alignLeft')}><FormatAlignLeftIcon /></ToggleButton>
      <ToggleButton value="center" aria-label={t('fontSettings.alignCenter')}><FormatAlignCenterIcon /></ToggleButton>
      <ToggleButton value="justify" aria-label={t('fontSettings.alignJustify')}><FormatAlignJustifyIcon /></ToggleButton>
      <ToggleButton value="right" aria-label={t('fontSettings.alignRight')}><FormatAlignRightIcon /></ToggleButton>
    </ToggleButtonGroup>
  );
};

export const ThemeModule = () => {
  const { t } = useTranslation();
  const theme = useSiteTheme();
  const { backgroundColor, fontColor } = useReaderSettings();
  const current = findReaderTheme(backgroundColor, fontColor);

  return (
    <Box role="group" aria-label={t('readerDisplay.modules.theme.label')} sx={{ display: 'flex', gap: 0.75 }}>
      {READER_THEMES.map((option) => {
        const selected = current?.labelKey === option.labelKey;
        // Auto is a diagonal of the site theme's paper and text colours
        const swatchBackground = option.backgroundColor
          ?? `linear-gradient(135deg, ${theme.palette.background.paper} 50%, ${theme.palette.text.primary} 50%)`;
        const swatchColor = option.fontColor ?? theme.palette.text.primary;
        return (
          <Button
            key={option.labelKey}
            aria-pressed={selected}
            variant={selected ? 'contained' : 'outlined'}
            onClick={() => {
              updateReaderSetting('backgroundColor', option.backgroundColor);
              updateReaderSetting('fontColor', option.fontColor);
            }}
            sx={{
              flex: 1,
              minWidth: 0,
              px: 0.5,
              flexDirection: 'column',
              gap: 0.5,
              ...(selected ? {} : { color: 'text.primary', borderColor: 'divider' }),
            }}
          >
            <Box
              aria-hidden="true"
              sx={{
                width: 36,
                height: 26,
                borderRadius: 1,
                display: 'grid',
                placeItems: 'center',
                fontWeight: 600,
                background: swatchBackground,
                color: swatchColor,
                border: 1,
                borderColor: 'divider',
              }}
            >
              Aa
            </Box>
            <Typography variant="caption" component="span" noWrap>{t(option.labelKey)}</Typography>
          </Button>
        );
      })}
    </Box>
  );
};

export const FontModule = () => {
  const { t } = useTranslation();
  const fontFamily = useReaderSettings().fontFamily;
  return (
    <Box role="group" aria-label={t('fontSettings.font')} sx={{ display: 'flex', gap: 1, overflowX: 'auto', pb: 0.5, scrollbarWidth: 'none', '&::-webkit-scrollbar': { display: 'none' } }}>
      {fontOptions.map((font) => {
        const selected = fontFamily === font.value;
        return (
          <Chip
            key={font.labelKey}
            label={t(font.labelKey)}
            clickable
            aria-pressed={selected}
            color={selected ? 'primary' : 'default'}
            variant={selected ? 'filled' : 'outlined'}
            onClick={() => updateReaderSetting('fontFamily', font.value)}
            sx={{ flexShrink: 0, fontFamily: font.value ?? undefined }}
          />
        );
      })}
    </Box>
  );
};

export const DimModule = () => {
  const { t } = useTranslation();
  const dimLevel = useReaderSettings().dimLevel;
  const label = t('readerDisplay.modules.dim.label');
  return (
    <ModuleRow>
      <Typography variant="body2" component="span" sx={{ whiteSpace: 'nowrap' }}>{label}</Typography>
      <LabelledSlider
        label={label}
        value={dimLevel}
        min={0}
        max={90}
        onChange={(value) => updateReaderSetting('dimLevel', value)}
      />
    </ModuleRow>
  );
};

export const WarmModule = () => {
  const { t } = useTranslation();
  const { nightMode, nightModeStrength } = useReaderSettings();
  const label = t('readerDisplay.modules.warm.label');
  return (
    <ModuleRow>
      <FormControlLabel
        control={
          <Switch
            checked={nightMode}
            onChange={(_event, checked) => updateReaderSetting('nightMode', checked)}
          />
        }
        label={t('readerDisplay.modules.warm.toggle')}
        sx={{ me: 0, whiteSpace: 'nowrap' }}
      />
      <LabelledSlider
        label={label}
        value={nightModeStrength}
        min={10}
        max={90}
        onChange={(value) => updateReaderSetting('nightModeStrength', value)}
      />
    </ModuleRow>
  );
};
