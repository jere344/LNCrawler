import type { ReactNode } from 'react';
import { Box, IconButton, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useReaderSettings } from '../hooks/useReaderSettings';
import { updateReaderSetting } from '../readerSettingsStore';
import type { ReaderSettings } from '../readerSettingsSchema';

// Settings that hold a plain number, so a stepper can write them
type NumericSettingKey = {
  [K in keyof ReaderSettings]: ReaderSettings[K] extends number ? K : never;
}[keyof ReaderSettings];

interface StepperProps {
  settingKey: NumericSettingKey;
  step: number;
  min: number;
  max: number;
  format: (value: number) => string;
  label: string;
  // Button contents; default to a minus and a plus sign
  decreaseLabel?: ReactNode;
  increaseLabel?: ReactNode;
  // Shown and stepped from instead of the stored value, when the stored value is clamped elsewhere
  value?: number;
}

const TARGET_SIZE = 44;
const MUTED_SX = { color: 'text.disabled' };

// Number of digits after the point in the step, so 0.1 rounds to one decimal
const decimalsOf = (step: number) => (String(step).split('.')[1] ?? '').length;

// A − value + control for one number setting. Writes through the settings store.
const Stepper = ({ settingKey, step, min, max, format, label, decreaseLabel = '−', increaseLabel = '+', value: shown }: StepperProps) => {
  const { t } = useTranslation();
  const stored = useReaderSettings()[settingKey] as number;
  const value = shown ?? stored;
  // At the limit the buttons stay focusable (aria-disabled), so focus is not lost on the press that reaches it
  const atMin = value <= min;
  const atMax = value >= max;

  const write = (next: number) => {
    const rounded = Number(next.toFixed(decimalsOf(step)));
    updateReaderSetting(settingKey, Math.min(max, Math.max(min, rounded)));
  };

  return (
    <Box role="group" aria-label={label} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
      <IconButton
        onClick={() => { if (!atMin) write(value - step); }}
        aria-disabled={atMin}
        aria-label={t('readerDisplay.decrease', { label })}
        sx={{ minWidth: TARGET_SIZE, minHeight: TARGET_SIZE, ...(atMin && MUTED_SX) }}
      >
        {decreaseLabel}
      </IconButton>
      <Typography component="output" aria-live="polite" sx={{ fontWeight: 600, textAlign: 'center', minWidth: 0 }}>
        {format(value)}
      </Typography>
      <IconButton
        onClick={() => { if (!atMax) write(value + step); }}
        aria-disabled={atMax}
        aria-label={t('readerDisplay.increase', { label })}
        sx={{ minWidth: TARGET_SIZE, minHeight: TARGET_SIZE, ...(atMax && MUTED_SX) }}
      >
        {increaseLabel}
      </IconButton>
    </Box>
  );
};

export default Stepper;
