import { useEffect, useState } from 'react';
import { Box, Button, ButtonBase, TextField, Typography } from '@mui/material';
import { decomposeColor, hslToRgb, rgbToHex } from '@mui/material/styles';
import { useTranslation } from 'react-i18next';
import { useReaderSettings } from '../hooks/useReaderSettings';
import { updateReaderSetting } from '../readerSettingsStore';
import { TOUCH_MIN_HEIGHT, TOUCH_TARGET } from '../touchTarget';

const HEX_CODE = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;
const SIX_DIGIT_HEX = /^#[0-9a-f]{6}$/i;

// The six-digit lowercase form of a valid code, so #fff is stored as #ffffff
const toSixDigits = (code: string) => {
  const hex = code.slice(1).toLowerCase();
  return hex.length === 3 ? `#${hex.split('').map((digit) => digit + digit).join('')}` : `#${hex}`;
};

// The native picker takes only six-digit hex: rgb() and hsl() colours are converted, anything else shows black
const toPickerHex = (color: string): string => {
  if (HEX_CODE.test(color)) return toSixDigits(color);
  try {
    const rgb = decomposeColor(color).type.startsWith('hsl') ? hslToRgb(color) : color;
    const hex = rgbToHex(rgb).slice(0, 7);
    return SIX_DIGIT_HEX.test(hex) ? hex : '#000000';
  } catch {
    return '#000000';
  }
};

type ColorSettingKey = 'backgroundColor' | 'fontColor';

interface ColorFieldProps {
  settingKey: ColorSettingKey;
  label: string;
  presets: string[];
  // Shown when the setting is unset, so the theme's colour
  fallback: string;
  // The data-setting-id of the row, for the settings search
  settingId?: string;
}

// One colour setting: swatches, a colour code and a native picker. Unset means the theme's colour.
const ColorField = ({ settingKey, label, presets, fallback, settingId }: ColorFieldProps) => {
  const { t } = useTranslation();
  const value = useReaderSettings()[settingKey];
  const shown = value ?? fallback;
  const [draft, setDraft] = useState(value ?? '');
  const draftValid = HEX_CODE.test(draft);

  // Follow changes from the swatches and the picker, but keep a typed code that already means the same colour
  useEffect(() => {
    setDraft((current) => (HEX_CODE.test(current) && toSixDigits(current) === value ? current : value ?? ''));
  }, [value]);

  const setColor = (color: string | null) => updateReaderSetting(settingKey, color);

  // A valid code applies as it is typed
  const onDraftChange = (text: string) => {
    setDraft(text);
    if (HEX_CODE.test(text)) setColor(toSixDigits(text));
  };

  // A code that is not valid goes back to the current colour
  const onDraftBlur = () => {
    if (!draftValid) setDraft(value ?? '');
  };

  return (
    <Box component="section" aria-label={label} data-setting-id={settingId} sx={{ py: 1.5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2, minHeight: TOUCH_MIN_HEIGHT }}>
        <Typography sx={{ fontWeight: 600 }}>{label}</Typography>
        {value ? (
          <Button size="small" onClick={() => setColor(null)} sx={{ minHeight: TOUCH_MIN_HEIGHT }}>
            {t('readerSettingsPages.colorDefault')}
          </Button>
        ) : (
          <Typography variant="body2" color="text.secondary">{t('readerSettingsPages.themeDefault')}</Typography>
        )}
      </Box>

      {/* The label stays in the text colour; the swatch shows the chosen colour */}
      <Box
        role="radiogroup"
        aria-label={t('readerSettingsPages.colorPresets', { label })}
        sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, my: 1 }}
      >
        {presets.map((preset) => {
          const selected = value === preset;
          return (
            <ButtonBase
              key={preset}
              role="radio"
              aria-checked={selected}
              aria-label={preset}
              onClick={() => setColor(preset)}
              sx={{ ...TOUCH_TARGET, borderRadius: '50%' }}
            >
              <Box
                aria-hidden="true"
                sx={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  backgroundColor: preset,
                  border: 1,
                  borderColor: 'divider',
                  outline: selected ? '2px solid' : 'none',
                  outlineColor: 'primary.main',
                  outlineOffset: '2px',
                }}
              />
            </ButtonBase>
          );
        })}
      </Box>

      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <TextField
          size="small"
          label={t('readerSettingsPages.colorCode')}
          value={draft}
          placeholder={fallback}
          onChange={(event) => onDraftChange(event.target.value)}
          onBlur={onDraftBlur}
          error={draft !== '' && !draftValid}
          helperText={draft !== '' && !draftValid ? t('readerSettingsPages.colorInvalid') : undefined}
          slotProps={{ htmlInput: { maxLength: 7, spellCheck: false, autoCapitalize: 'off', autoComplete: 'off' } }}
          sx={{ flex: 1, minWidth: 0 }}
        />
        <Box component="label" sx={{ position: 'relative', ...TOUCH_TARGET, flexShrink: 0, cursor: 'pointer' }}>
          <Box
            component="input"
            type="color"
            aria-label={t('readerSettingsPages.colorPicker', { label })}
            value={toPickerHex(shown)}
            onChange={(event) => setColor(event.target.value)}
            sx={{ position: 'absolute', inset: 0, width: '100%', height: '100%', p: 0, border: 0, opacity: 0, cursor: 'pointer' }}
          />
          <Box
            aria-hidden="true"
            sx={{ position: 'absolute', inset: 10, borderRadius: 1, border: 1, borderColor: 'divider', backgroundColor: shown, pointerEvents: 'none' }}
          />
        </Box>
      </Box>
    </Box>
  );
};

export default ColorField;
