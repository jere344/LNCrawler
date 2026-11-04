import { Box, ButtonBase, Divider, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import DirectionalIcon from '../DirectionalIcon';
import { useReaderSettings } from '../hooks/useReaderSettings';
import { findReaderTheme, fontOptions } from '../readerOptions';
import { SETTINGS_PAGES, type SettingsPageId } from './settingsPages';
import { SettingGroupHeading } from './SettingRows';
import BackupPage from './pages/BackupPage';

interface HomeRowProps {
  page: SettingsPageId;
  sub: string;
  onOpen: (page: SettingsPageId) => void;
}

// A row that opens a page: icon, title, a live sub line and a chevron
const HomeRow = ({ page, sub, onOpen }: HomeRowProps) => {
  const { t } = useTranslation();
  const { Icon, titleKey } = SETTINGS_PAGES[page];
  return (
    <ButtonBase
      onClick={() => onOpen(page)}
      sx={{ display: 'flex', width: '100%', alignItems: 'center', gap: 2, py: 1.5, textAlign: 'start', borderRadius: 1 }}
    >
      <Icon color="primary" />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontWeight: 600 }}>{t(titleKey)}</Typography>
        <Typography variant="body2" color="text.secondary" noWrap>{sub}</Typography>
      </Box>
      <DirectionalIcon><ChevronRightIcon color="action" /></DirectionalIcon>
    </ButtonBase>
  );
};

// The top of the settings panel on phones and tablets: pages with live sub lines, then backup
const SettingsHome = ({ onOpen }: { onOpen: (page: SettingsPageId) => void }) => {
  const { t } = useTranslation();
  const settings = useReaderSettings();

  const theme = findReaderTheme(settings.backgroundColor, settings.fontColor);
  const fontLabelKey = fontOptions.find((font) => font.value === settings.fontFamily)?.labelKey;

  return (
    <Box>
      <SettingGroupHeading>{t('readerSettingsPages.display')}</SettingGroupHeading>
      <HomeRow
        page="custom"
        onOpen={onOpen}
        sub={t('readerSettingsPages.sheetCount', { count: settings.displaySheetModules.length })}
      />
      <HomeRow
        page="text"
        onOpen={onOpen}
        sub={t('readerSettingsPages.textSub', {
          size: settings.fontSize,
          font: t(fontLabelKey ?? 'fontSettings.defaultThemeFont'),
          lines: settings.lineSpacing.toFixed(1),
        })}
      />
      <HomeRow
        page="colors"
        onOpen={onOpen}
        sub={t('readerSettingsPages.colorsSub', {
          theme: theme ? t(theme.labelKey) : t('readerSettingsPages.customTheme'),
          night: settings.nightMode
            ? t('readerSettingsPages.nightStrength', { strength: settings.nightModeStrength })
            : t('readerSettingsPages.nightOff'),
          scheduled: settings.nightMode && settings.nightModeScheduleEnabled ? t('readerSettingsPages.scheduled') : '',
        })}
      />

      <SettingGroupHeading>{t('readerSettingsPages.controls')}</SettingGroupHeading>
      <HomeRow
        page="touch"
        onOpen={onOpen}
        sub={t('readerSettingsPages.touchSub', {
          trigger: t(`readerSettingsPages.trigger.${settings.controlsTrigger}`),
          side: t(`readerSettingsPages.dimSide.${settings.dimGestureSide}`),
        })}
      />
      <HomeRow
        page="keys"
        onOpen={onOpen}
        sub={settings.keyboardNavigation ? t('readerSettingsPages.keysOn') : t('readerSettingsPages.keysOff')}
      />
      <HomeRow
        page="reading"
        onOpen={onOpen}
        sub={t('readerSettingsPages.readingSub', {
          header: t(settings.readerHeaderBehavior === 'pageTop'
            ? 'readerSettingsPages.headerPageTop'
            : 'readerSettingsPages.headerReappear'),
        })}
      />
      <HomeRow page="listen" onOpen={onOpen} sub={t('readerSettingsPages.listenSub')} />

      <Divider sx={{ my: 2 }} />
      <BackupPage />
    </Box>
  );
};

export default SettingsHome;
