import { Box, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { SettingSelect, SettingSwitch } from '../SettingRows';
import { READER_KEYS } from '../../hooks/useReaderActions';
import { useReaderSettings } from '../../hooks/useReaderSettings';
import type { KeyAction } from '../../readerSettingsSchema';

const ACTION_LABEL_KEYS: { value: KeyAction; labelKey: string }[] = [
  { value: 'none', labelKey: 'keyboardSettings.doNothing' },
  { value: 'scrollUp', labelKey: 'keyboardSettings.scrollUp' },
  { value: 'scrollDown', labelKey: 'keyboardSettings.scrollDown' },
  { value: 'prevChapter', labelKey: 'keyboardSettings.previousChapter' },
  { value: 'nextChapter', labelKey: 'keyboardSettings.nextChapter' },
  { value: 'toggleControls', labelKey: 'readerSettingsPages.keyActions.toggleControls' },
  { value: 'displaySheet', labelKey: 'readerSettingsPages.keyActions.displaySheet' },
  { value: 'fullscreen', labelKey: 'readerSettingsPages.keyActions.fullscreen' },
  { value: 'comments', labelKey: 'readerSettingsPages.keyActions.comments' },
];

// The master switch, then one action per key. Off greys the keys out.
const KeyboardPage = () => {
  const { t } = useTranslation();
  const { keyboardNavigation } = useReaderSettings();
  const actionOptions = ACTION_LABEL_KEYS.map(({ value, labelKey }) => ({ value, label: t(labelKey) }));

  return (
    <Box>
      <SettingSwitch
        settingKey="keyboardNavigation"
        settingId="keyboardNavigation"
        title={t('keyboardSettings.enable')}
        sub={t('readerSettingsPages.keysSub')}
      />
      {READER_KEYS.map(({ setting, labelKey }) => (
        <SettingSelect
          key={setting}
          settingKey={setting}
          settingId={setting}
          title={t(labelKey)}
          options={actionOptions}
          disabled={!keyboardNavigation}
        />
      ))}
      <Typography variant="body2" color="text.secondary" sx={{ pt: 2 }}>
        {t('readerSettingsPages.escNote')}
      </Typography>
    </Box>
  );
};

export default KeyboardPage;
