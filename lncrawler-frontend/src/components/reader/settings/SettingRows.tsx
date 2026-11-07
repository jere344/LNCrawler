import type { ComponentProps, ReactNode } from 'react';
import { Box, Button, MenuItem, Select, Switch, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useReaderSettings } from '../hooks/useReaderSettings';
import { updateReaderSetting } from '../readerSettingsStore';
import { defaultSettings } from '../readerDefaults';
import type { ReaderSettings } from '../readerSettingsSchema';
import Stepper from '../display/Stepper';

// Settings that hold a true or false value, so a switch can write them
type BooleanSettingKey = {
  [K in keyof ReaderSettings]: ReaderSettings[K] extends boolean ? K : never;
}[keyof ReaderSettings];

// Settings that hold a text value, so a select can write them
type TextSettingKey = {
  [K in keyof ReaderSettings]: ReaderSettings[K] extends string | null ? K : never;
}[keyof ReaderSettings];

interface SettingRowProps {
  title: string;
  sub?: string;
  control: ReactNode;
  // Jump target for the settings search
  settingId?: string;
}

// One setting: title and optional sub line on the left, its control on the right
export const SettingRow = ({ title, sub, control, settingId }: SettingRowProps) => (
  <Box
    data-setting-id={settingId}
    sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2, py: 1.5, minHeight: 48 }}
  >
    <Box sx={{ minWidth: 0 }}>
      <Typography sx={{ fontWeight: 600 }}>{title}</Typography>
      {sub && <Typography variant="body2" color="text.secondary">{sub}</Typography>}
    </Box>
    <Box sx={{ flexShrink: 0 }}>{control}</Box>
  </Box>
);

interface SettingSwitchProps {
  settingKey: BooleanSettingKey;
  title: string;
  sub?: string;
  settingId?: string;
}

export const SettingSwitch = ({ settingKey, title, sub, settingId }: SettingSwitchProps) => {
  const checked = useReaderSettings()[settingKey];
  return (
    <SettingRow
      title={title}
      sub={sub}
      settingId={settingId}
      control={
        <Switch
          checked={checked}
          onChange={(event) => updateReaderSetting(settingKey, event.target.checked)}
          slotProps={{ input: { 'aria-label': title } }}
        />
      }
    />
  );
};

interface SettingSelectProps {
  settingKey: TextSettingKey;
  title: string;
  options: { value: string; label: string; disabled?: boolean }[];
  sub?: string;
  settingId?: string;
  disabled?: boolean;
}

export const SettingSelect = ({ settingKey, title, options, sub, settingId, disabled }: SettingSelectProps) => {
  const value = String(useReaderSettings()[settingKey] ?? '');
  return (
    <SettingRow
      title={title}
      sub={sub}
      settingId={settingId}
      control={
        <Select
          size="small"
          value={value}
          displayEmpty
          disabled={disabled}
          onChange={(event) => updateReaderSetting(settingKey, event.target.value as ReaderSettings[TextSettingKey])}
          SelectDisplayProps={{ 'aria-label': title }}
          sx={{ minWidth: 160 }}
        >
          {options.map((option) => (
            <MenuItem key={option.value} value={option.value} disabled={option.disabled}>{option.label}</MenuItem>
          ))}
        </Select>
      }
    />
  );
};

type StepperProps = ComponentProps<typeof Stepper>;

interface SettingStepperProps extends Omit<StepperProps, 'label'> {
  title: string;
  // The accessible name of the stepper; the title when not given
  label?: string;
  sub?: string;
  settingId?: string;
}

// A stepper setting: the Stepper sits in a row with its title
export const SettingStepper = ({ title, label = title, sub, settingId, ...stepper }: SettingStepperProps) => (
  <SettingRow title={title} sub={sub} settingId={settingId} control={<Box sx={{ width: 180 }}><Stepper label={label} {...stepper} /></Box>} />
);

export const SettingGroupHeading = ({ children }: { children: ReactNode }) => (
  <Typography variant="overline" component="h3" color="text.secondary" sx={{ display: 'block', pt: 2, pb: 0.5 }}>
    {children}
  </Typography>
);

// Restores the listed settings to their defaults, for a page's reset button
export const PageFootReset = ({ keys }: { keys: (keyof ReaderSettings)[] }) => {
  const { t } = useTranslation();
  const resetPage = () => {
    keys.forEach((key) => updateReaderSetting(key, defaultSettings[key]));
  };

  return (
    <Box sx={{ pt: 2 }}>
      <Button variant="outlined" onClick={resetPage}>{t('readerSettingsPages.resetPage')}</Button>
    </Box>
  );
};
