import { Box, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { SettingGroupHeading, SettingSelect, SettingSwitch } from '../SettingRows';
import { useReaderSettings } from '../../hooks/useReaderSettings';
import { updateReaderSetting } from '../../readerSettingsStore';
import type { MarkReadBehavior, ReaderHeaderBehavior, ReadingMode } from '../../readerSettingsSchema';
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

const READING_MODE_LABEL_KEYS: Record<ReadingMode, string> = {
  chapter: 'behaviorSettings.readingModeChapter',
  infinite: 'behaviorSettings.readingModeInfinite',
};

// What each reading mode does, shown under the select
const READING_MODE_HINT_KEYS: Record<ReadingMode, string> = {
  chapter: 'behaviorSettings.readingModeChapterHint',
  infinite: 'behaviorSettings.readingModeInfiniteHint',
};

const READING_MODES = Object.keys(READING_MODE_LABEL_KEYS) as ReadingMode[];

// How the site header behaves over the chapter, and the reading behaviour switches
const ReadingPage = () => {
  const { t } = useTranslation();
  const { readerHeaderBehavior, markReadBehavior, readingMode } = useReaderSettings();
  const { mode, isAuthenticated } = useSettingsContext();
  const markReadOptions = MARK_READ_BEHAVIORS.map((behavior) => ({
    value: behavior,
    label: t(MARK_READ_LABEL_KEYS[behavior]),
  }));
  const readingModeOptions = READING_MODES.map((option) => ({
    value: option,
    label: t(READING_MODE_LABEL_KEYS[option]),
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
      <SettingSelect
        settingKey="readingMode"
        settingId="readingMode"
        title={t('behaviorSettings.readingMode')}
        sub={t(READING_MODE_HINT_KEYS[readingMode])}
        options={readingModeOptions}
      />
      {readingMode === 'infinite' && (
        <SettingSwitch
          settingKey="infiniteShowComments"
          settingId="infiniteShowComments"
          title={t('behaviorSettings.infiniteShowComments')}
          sub={t('behaviorSettings.infiniteShowCommentsHint')}
        />
      )}
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
