import { Box, Chip, TextField, Typography } from '@mui/material';
import { getContrastRatio } from '@mui/material/styles';
import { useTranslation } from 'react-i18next';
import SimulatedPreview from '../SimulatedPreview';
import ColorField from '../ColorField';
import { SettingGroupHeading, SettingRow, SettingStepper, SettingSwitch } from '../SettingRows';
import { ThemeModule } from '../../display/moduleControls';
import { STEPPER_SPECS } from '../../display/stepperSpecs';
import { BACKGROUND_COLOR_PRESETS, TEXT_COLOR_PRESETS } from '../../readerOptions';
import { useReaderSettings } from '../../hooks/useReaderSettings';
import { updateReaderSetting } from '../../readerSettingsStore';
import { useSiteTheme } from '../../theme/siteTheme';

// A complete HH:MM value. A half-typed time keeps the stored one.
const TIME_PATTERN = /^\d{2}:\d{2}$/;

// WCAG contrast ratio, or undefined when a colour cannot be read
const contrastRatioOf = (a: string, b: string): number | undefined => {
  try {
    return getContrastRatio(a, b);
  } catch {
    return undefined;
  }
};

// Colour theme, the two colour fields, a readability note and the night filter
const ColorsPage = () => {
  const { t } = useTranslation();
  const settings = useReaderSettings();
  const theme = useSiteTheme();

  // What the reader shows when a colour is unset
  const background = settings.backgroundColor ?? theme.palette.background.paper;
  const text = settings.fontColor ?? theme.palette.text.primary;
  const ratio = contrastRatioOf(background, text);
  const meetsRecommended = ratio !== undefined && ratio >= 4.5;

  const screenDimTitle = t('readerSettingsPages.screenDim');
  const strengthTitle = t('readerSettingsPages.strength');
  const startTitle = t('readerSettingsPages.from');
  const endTitle = t('readerSettingsPages.until');

  // One row of the night schedule: a time field that keeps the stored value until a complete HH:MM is typed
  const renderTimeRow = (title: string, settingKey: 'nightModeStartTime' | 'nightModeEndTime', ariaLabel: string) => (
    <SettingRow
      title={title}
      control={
        <TextField
          type="time"
          size="small"
          value={settings[settingKey]}
          onChange={(event) => {
            if (TIME_PATTERN.test(event.target.value)) updateReaderSetting(settingKey, event.target.value);
          }}
          slotProps={{ htmlInput: { 'aria-label': ariaLabel } }}
        />
      }
    />
  );

  return (
    <Box>
      <SimulatedPreview />

      <Box sx={{ pt: 2 }} data-setting-id="colorTheme">
        <Typography sx={{ fontWeight: 600, pb: 1 }}>{t('readerSettingsPages.colorTheme')}</Typography>
        <ThemeModule />
      </Box>

      <ColorField
        settingKey="backgroundColor"
        settingId="backgroundColor"
        label={t('colorSettings.background')}
        presets={BACKGROUND_COLOR_PRESETS}
        fallback={theme.palette.background.paper}
      />
      <ColorField
        settingKey="fontColor"
        settingId="fontColor"
        label={t('readerSettingsPages.textLabel')}
        presets={TEXT_COLOR_PRESETS}
        fallback={theme.palette.text.primary}
      />

      {/* A note only: the reader never blocks or corrects a low contrast choice */}
      <SettingRow
        settingId="readability"
        title={t('readerSettingsPages.readability')}
        sub={ratio === undefined ? undefined : meetsRecommended ? t('readerSettingsPages.contrastMeets') : t('readerSettingsPages.contrastBelow')}
        control={
          ratio === undefined ? null : (
            <Chip
              size="small"
              variant="outlined"
              label={`${ratio.toFixed(1)}:1`}
              color={meetsRecommended ? 'success' : 'warning'}
            />
          )
        }
      />

      <SettingGroupHeading>{t('readerSettingsPages.nightMode')}</SettingGroupHeading>
      <SettingStepper
        title={screenDimTitle}
        sub={t('readerSettingsPages.screenDimSub')}
        settingKey="dimLevel"
        settingId="dimLevel"
        {...STEPPER_SPECS.dimLevel}
      />
      <SettingSwitch
        settingKey="nightMode"
        settingId="nightMode"
        title={t('readerSettingsPages.nightFilter')}
        sub={t('readerSettingsPages.nightFilterSub')}
      />
      {settings.nightMode && (
        <>
          <SettingStepper
            title={strengthTitle}
            settingKey="nightModeStrength"
            settingId="nightModeStrength"
            {...STEPPER_SPECS.nightModeStrength}
          />
          <SettingSwitch settingKey="nightModeScheduleEnabled" settingId="nightSchedule" title={t('readerSettingsPages.onSchedule')} />
        </>
      )}
      {settings.nightMode && settings.nightModeScheduleEnabled && (
        <>
          {renderTimeRow(startTitle, 'nightModeStartTime', t('readerSettingsPages.startTimeLabel'))}
          {renderTimeRow(endTitle, 'nightModeEndTime', t('readerSettingsPages.endTimeLabel'))}
        </>
      )}
    </Box>
  );
};

export default ColorsPage;
