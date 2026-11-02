import { Box, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { SettingGroupHeading, SettingSelect, SettingSwitch } from '../SettingRows';
import { useReaderSettings } from '../../hooks/useReaderSettings';
import { updateReaderSetting } from '../../readerSettingsStore';
import type { MarkReadBehavior, ReaderHeaderBehavior } from '../../readerSettingsSchema';
import { useSettingsContext } from '../settingsContext';

const MARK_READ_LABEL_KEYS: Record<MarkReadBehavior, string> = {
  none: 'behaviorSettings.none',
  button: 'behaviorSettings.buttonOnly',
  automatic: 'behaviorSettings.automatic',
  buttonAutomatic: 'behaviorSettings.buttonAndAutomatic',
};

// What each mark-as-read choice does, shown under the select
const MARK_READ_HINT_KEYS: Record<MarkReadBehavior, string> = {
  none: 'behaviorSettings.hidden',
  button: 'behaviorSettings.shownNotAuto',
  automatic: 'behaviorSettings.autoPrev',
  buttonAutomatic: 'behaviorSettings.bothEnabled',
};

const MARK_READ_BEHAVIORS = Object.keys(MARK_READ_LABEL_KEYS) as MarkReadBehavior[];

// How the site header behaves over the chapter, and the reading behaviour switches
const ReadingPage = () => {
  const { t } = useTranslation();
  const { readerHeaderBehavior, markReadBehavior } = useReaderSettings();
  const { mode, isAuthenticated } = useSettingsContext();
  const markReadOptions = MARK_READ_BEHAVIORS.map((behavior) => ({
    value: behavior,
    label: t(MARK_READ_LABEL_KEYS[behavior]),
  }));

  return (
    <Box>
      <SettingGroupHeading>{t('readerSettingsPages.siteHeader')}</SettingGroupHeading>
      {mode === 'desktop' ? (
        <Typography variant="body2" color="text.secondary">{t('readerSettingsPages.headerDesktopNote')}</Typography>
      ) : (
        <>
          <ToggleButtonGroup
            exclusive
            fullWidth
            size="small"
            aria-label={t('readerSettingsPages.siteHeader')}
            data-setting-id="readerHeaderBehavior"
            value={readerHeaderBehavior}
            onChange={(_, value: ReaderHeaderBehavior | null) => {
              if (value) updateReaderSetting('readerHeaderBehavior', value);
            }}
          >
            <ToggleButton value="reappear">{t('readerSettingsPages.headerReappears')}</ToggleButton>
            <ToggleButton value="pageTop">{t('readerSettingsPages.headerTop')}</ToggleButton>
          </ToggleButtonGroup>
          <Typography variant="body2" color="text.secondary" sx={{ pt: 1 }}>
            {readerHeaderBehavior === 'pageTop'
              ? t('readerSettingsPages.headerPageTopHint')
              : t('readerSettingsPages.headerReappearHint')}
          </Typography>
        </>
      )}

      <SettingGroupHeading>{t('readerSettingsPages.behaviour')}</SettingGroupHeading>
      {isAuthenticated && (
        <SettingSelect
          settingKey="markReadBehavior"
          settingId="markReadBehavior"
          title={t('behaviorSettings.markAsReadBehavior')}
          sub={t(MARK_READ_HINT_KEYS[markReadBehavior])}
          options={markReadOptions}
        />
      )}
      <SettingSwitch settingKey="textSelectable" settingId="textSelectable" title={t('behaviorSettings.allowSelection')} />
      <SettingSwitch settingKey="savePosition" settingId="savePosition" title={t('behaviorSettings.rememberPosition')} />
      <SettingSwitch
        settingKey="hideScrollbar"
        settingId="hideScrollbar"
        title={t('layoutSettings.hideScrollbar')}
        sub={t('layoutSettings.hideScrollbarHint')}
      />
    </Box>
  );
};

export default ReadingPage;
