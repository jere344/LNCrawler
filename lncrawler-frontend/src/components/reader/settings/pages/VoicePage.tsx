import { useMemo } from 'react';
import { Box, FormHelperText, ToggleButton, ToggleButtonGroup } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { SettingGroupHeading, SettingSelect, SettingStepper, SettingSwitch } from '../SettingRows';
import { useReaderSettings } from '../../hooks/useReaderSettings';
import { updateReaderSetting } from '../../readerSettingsStore';
import { neuralOptions, neuralOptionsKey, type TtsEngineChoice } from '../../tts/ttsTypes';
import { getNeuralVoicesForLang, resolveNeuralVoice } from '../../tts/voiceCatalog';
import { isNeuralSupported } from '../../tts/neuralClient';
import { availableLanguages } from '@utils/Misc';
import { useNeuralModels } from '../useNeuralModels';
import { useModelFamily } from '../tts/useModelFamily';
import BrowserVoicePicker from '../tts/BrowserVoicePicker';
import HdVoicePicker from '../tts/HdVoicePicker';
import HdPerformance from '../tts/HdPerformance';
import { useSettingsContext } from '../settingsContext';

const HIGHLIGHT_LABEL_KEYS = {
  sentence: 'ttsSettings.highlightSentence',
  paragraph: 'ttsSettings.highlightParagraph',
  none: 'ttsSettings.highlightNone',
} as const;

// The quality of the voice (device or HD), the voice and how it reads, and the performance of HD voices
const VoicePage = () => {
  const { t } = useTranslation();
  const settings = useReaderSettings();
  const { novelLanguage } = useSettingsContext();
  const lang = settings.ttsLanguage || novelLanguage;
  const isHd = settings.ttsEngine === 'neural';
  const languageName = t(`languages.${lang}`, { defaultValue: lang });
  const neuralSupported = isNeuralSupported();
  const neuralVoices = useMemo(() => getNeuralVoicesForLang(lang), [lang]);
  const selectedNeural = resolveNeuralVoice(lang, settings.ttsNeuralVoices);
  const optionsKey = neuralOptionsKey(neuralOptions(settings));
  // eslint-disable-next-line react-hooks/exhaustive-deps -- recomputed from its key
  const options = useMemo(() => neuralOptions(settings), [optionsKey]);
  const family = useModelFamily(lang, neuralVoices, settings.ttsNeuralVoices);
  const models = useNeuralModels({
    ttsEngine: settings.ttsEngine,
    neuralSupported,
    neuralVoices,
    options,
    selectedNeuralId: selectedNeural?.id,
  });

  const languageOptions = [
    { value: '', label: t('ttsSettings.languageAuto', { language: t(`languages.${novelLanguage}`, { defaultValue: novelLanguage }) }) },
    ...availableLanguages.map(code => ({ value: code, label: t(`languages.${code}`) })),
  ];
  const highlightOptions = (Object.keys(HIGHLIGHT_LABEL_KEYS) as (keyof typeof HIGHLIGHT_LABEL_KEYS)[])
    .map(value => ({ value, label: t(HIGHLIGHT_LABEL_KEYS[value]) }));

  return (
    <Box>
      <SettingGroupHeading>{t('ttsSettings.quality')}</SettingGroupHeading>
      <ToggleButtonGroup
        exclusive
        fullWidth
        size="small"
        aria-label={t('ttsSettings.quality')}
        data-setting-id="ttsEngine"
        value={settings.ttsEngine}
        onChange={(_, value: TtsEngineChoice | null) => {
          if (value) updateReaderSetting('ttsEngine', value);
        }}
      >
        <ToggleButton value="browser">{t('ttsSettings.qualityStandard')}</ToggleButton>
        <ToggleButton value="neural" disabled={!neuralSupported}>{t('ttsSettings.qualityHd')}</ToggleButton>
      </ToggleButtonGroup>
      <FormHelperText sx={{ mb: 1 }}>
        {isHd ? t('ttsSettings.qualityHdHint') : t('ttsSettings.qualityStandardHint')}
      </FormHelperText>

      <SettingGroupHeading>{t('ttsSettings.voiceFor', { language: languageName })}</SettingGroupHeading>
      <SettingSelect
        settingKey="ttsLanguage"
        settingId="ttsLanguage"
        title={t('ttsSettings.language')}
        sub={t('ttsSettings.languageHint')}
        options={languageOptions}
      />
      {isHd
        ? <HdVoicePicker lang={lang} neuralVoices={neuralVoices} options={options} models={models} family={family} />
        : <BrowserVoicePicker lang={lang} />}
      {isHd ? (
        <SettingStepper
          settingKey="ttsVolume"
          settingId="ttsVolume"
          title={t('ttsSettings.volume')}
          step={0.1}
          min={0}
          max={1}
          format={v => `${Math.round(v * 100)}%`}
        />
      ) : (
        <SettingStepper
          settingKey="ttsPitch"
          settingId="ttsPitch"
          title={t('ttsSettings.pitch')}
          step={0.1}
          min={0.5}
          max={2}
          format={v => v.toFixed(1)}
        />
      )}
      <SettingStepper
        settingKey="ttsParagraphPause"
        settingId="ttsParagraphPause"
        title={t('ttsSettings.paragraphPause')}
        step={50}
        min={0}
        max={2000}
        format={ms => t('ttsSettings.milliseconds', { value: ms })}
      />

      <SettingGroupHeading>{t('ttsSettings.readingAlong')}</SettingGroupHeading>
      <SettingSelect
        settingKey="ttsHighlight"
        settingId="ttsHighlight"
        title={t('ttsSettings.highlight')}
        options={highlightOptions}
      />
      <SettingSwitch
        settingKey="ttsAutoScroll"
        settingId="ttsAutoScroll"
        title={t('ttsSettings.autoScroll')}
        sub={t('ttsSettings.autoScrollHint')}
      />
      <SettingSwitch
        settingKey="ttsTapToSeek"
        settingId="ttsTapToSeek"
        title={t('ttsSettings.tapToSeek')}
        sub={t('ttsSettings.tapToSeekHint')}
      />
      <SettingSwitch settingKey="ttsReadTitle" settingId="ttsReadTitle" title={t('ttsSettings.readTitle')} />
      <SettingSwitch
        settingKey="ttsSkipNotes"
        settingId="ttsSkipNotes"
        title={t('ttsSettings.skipNotes')}
        sub={t('ttsSettings.skipNotesHint')}
      />

      {isHd && neuralVoices.length > 0 && (
        <>
          <SettingGroupHeading>{t('ttsSettings.performance')}</SettingGroupHeading>
          <HdPerformance visibleFamily={family.visibleFamily} />
        </>
      )}
    </Box>
  );
};

export default VoicePage;
