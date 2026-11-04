import { Box, ButtonBase, FormControlLabel, Radio, RadioGroup, Typography } from '@mui/material';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { useTranslation } from 'react-i18next';
import { SettingGroupHeading, SettingStepper, SettingSwitch } from '../SettingRows';
import DirectionalIcon from '../../DirectionalIcon';
import { useReaderSettings } from '../../hooks/useReaderSettings';
import { updateReaderSetting } from '../../readerSettingsStore';
import { useSettingsContext } from '../settingsContext';

// The audiobook or the device voice reads the chapter, the voice settings, and the playback settings
const ListeningPage = () => {
  const { t } = useTranslation();
  const { ttsPreferAudiobook, ttsEngine, ttsHighlight } = useReaderSettings();
  const { hasNarration, chapterNumber, onOpenPage } = useSettingsContext();
  const voiceSub = `${t(ttsEngine === 'neural' ? 'ttsSettings.qualityHd' : 'ttsSettings.qualityStandard')} · ${t(
    ttsHighlight === 'none' ? 'ttsSettings.highlightOff' : 'ttsSettings.highlightOn',
  )}`;

  return (
    <Box>
      {chapterNumber !== undefined && (
        <Box sx={{ p: 2, mt: 1, borderRadius: 1, bgcolor: 'action.hover' }}>
          <Typography sx={{ fontWeight: 600 }}>
            {hasNarration
              ? t('ttsSettings.chapterAudiobook', { number: chapterNumber })
              : t('ttsSettings.chapterNoAudiobook', { number: chapterNumber })}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {hasNarration ? t('ttsSettings.audiobookSub') : t('ttsSettings.deviceVoiceSub')}
          </Typography>
        </Box>
      )}

      <SettingGroupHeading>{t('ttsSettings.whatReads')}</SettingGroupHeading>
      <RadioGroup
        aria-label={t('ttsSettings.whatReads')}
        data-setting-id="ttsPreferAudiobook"
        value={ttsPreferAudiobook ? 'audiobook' : 'device'}
        onChange={(_, value) => updateReaderSetting('ttsPreferAudiobook', value === 'audiobook')}
      >
        <FormControlLabel
          value="audiobook"
          control={<Radio />}
          sx={{ alignItems: 'flex-start', py: 0.5 }}
          label={
            <Box component="span" sx={{ display: 'block' }}>
              <Typography component="span" sx={{ display: 'block', fontWeight: 600 }}>{t('ttsSettings.audiobookWhenThere')}</Typography>
              <Typography component="span" variant="body2" color="text.secondary" sx={{ display: 'block' }}>
                {t('ttsSettings.audiobookWhenThereHint')}
              </Typography>
            </Box>
          }
        />
        <FormControlLabel
          value="device"
          control={<Radio />}
          sx={{ alignItems: 'flex-start', py: 0.5 }}
          label={
            <Box component="span" sx={{ display: 'block' }}>
              <Typography component="span" sx={{ display: 'block', fontWeight: 600 }}>{t('ttsSettings.alwaysDevice')}</Typography>
              <Typography component="span" variant="body2" color="text.secondary" sx={{ display: 'block' }}>
                {t('ttsSettings.alwaysDeviceHint')}
              </Typography>
            </Box>
          }
        />
      </RadioGroup>
      {ttsPreferAudiobook && (
        <Typography variant="body2" color="text.secondary">{t('ttsSettings.deviceFallback')}</Typography>
      )}

      <SettingGroupHeading>{t('ttsSettings.audiobookSection')}</SettingGroupHeading>
      <Typography variant="body2" color="text.secondary">{t('ttsSettings.audiobookPlayerNote')}</Typography>

      <SettingGroupHeading>{t('ttsSettings.deviceVoice')}</SettingGroupHeading>
      <ButtonBase
        onClick={() => onOpenPage('voice')}
        sx={{ display: 'flex', width: '100%', alignItems: 'center', gap: 2, py: 1.5, textAlign: 'start', borderRadius: 1 }}
      >
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 600 }}>{t('readerSettingsPages.pages.voice')}</Typography>
          <Typography variant="body2" color="text.secondary" noWrap>{voiceSub}</Typography>
        </Box>
        <DirectionalIcon><ChevronRightIcon color="action" /></DirectionalIcon>
      </ButtonBase>
      <SettingStepper
        settingKey="ttsRate"
        settingId="ttsRate"
        title={t('ttsSettings.speed')}
        label={t('ttsSettings.speed')}
        step={0.25}
        min={0.5}
        max={3}
        format={rate => `${rate.toFixed(2)}×`}
      />
      <SettingSwitch settingKey="ttsAutoNextChapter" settingId="ttsAutoNextChapter" title={t('ttsSettings.autoNextChapter')} />
      <SettingSwitch settingKey="ttsKeepScreenOn" settingId="ttsKeepScreenOn" title={t('ttsSettings.keepScreenOn')} sub={t('ttsSettings.keepScreenOnHint')} />
    </Box>
  );
};

export default ListeningPage;
