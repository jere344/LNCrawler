import { Box, FormHelperText, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { SettingSelect } from '../SettingRows';
import { useReaderSettings } from '../../hooks/useReaderSettings';
import { updateReaderSetting } from '../../readerSettingsStore';
import { KOKORO_SIZE_MB, SUPERTONIC_LICENSE_URL, SUPERTONIC_STEPS, type NeuralEngine } from '../../tts/voiceCatalog';
import { hasWebGpu } from './ttsShared';

interface HdPerformanceProps {
  // The model family on screen: its own processing options are shown, the others are not
  visibleFamily: NeuralEngine;
}

// How hard the HD voices work the device: denoising steps, processor, and the pause between generations
const HdPerformance = ({ visibleFamily }: HdPerformanceProps) => {
  const { t } = useTranslation();
  const { ttsSupertonicSteps } = useReaderSettings();

  return (
    <>
      {visibleFamily === 'supertonic' && (
        <>
          <Box data-setting-id="ttsQuality" sx={{ py: 1.5 }}>
            <Typography sx={{ fontWeight: 600, mb: 1 }}>{t('ttsSettings.processingQuality')}</Typography>
            <ToggleButtonGroup
              exclusive
              fullWidth
              size="small"
              aria-label={t('ttsSettings.processingQuality')}
              value={ttsSupertonicSteps}
              onChange={(_, v) => v && updateReaderSetting('ttsSupertonicSteps', v)}
            >
              <ToggleButton value={SUPERTONIC_STEPS.fast}>{t('ttsSettings.qualityFast')}</ToggleButton>
              <ToggleButton value={SUPERTONIC_STEPS.balanced}>{t('ttsSettings.qualityBalanced')}</ToggleButton>
              <ToggleButton value={SUPERTONIC_STEPS.best}>{t('ttsSettings.qualityBest')}</ToggleButton>
            </ToggleButtonGroup>
            <FormHelperText>{t('ttsSettings.qualityHint')}</FormHelperText>
          </Box>
          <SettingSelect
            settingKey="ttsSupertonicDevice"
            title={t('ttsSettings.supertonicDevice')}
            options={[
              { value: 'auto', label: t('ttsSettings.deviceAuto') },
              { value: 'wasm', label: t('ttsSettings.deviceCpuShort') },
              { value: 'webgpu', label: t('ttsSettings.deviceGpuShort'), disabled: !hasWebGpu() },
            ]}
          />
          <Typography variant="caption" component="p" color="text.secondary" sx={{ mt: 1 }}>
            <a href={SUPERTONIC_LICENSE_URL} target="_blank" rel="noopener noreferrer" style={{ color: 'inherit' }}>
              {t('ttsSettings.modelLicense')}
            </a>
          </Typography>
        </>
      )}

      {visibleFamily === 'kokoro' && (
        <SettingSelect
          settingKey="ttsKokoroDevice"
          title={t('ttsSettings.kokoroDevice')}
          sub={t('ttsSettings.kokoroDeviceHint')}
          options={[
            { value: 'wasm', label: t('ttsSettings.deviceCpu', { size: KOKORO_SIZE_MB.wasm }) },
            { value: 'webgpu', label: t('ttsSettings.deviceGpu', { size: KOKORO_SIZE_MB.webgpu }), disabled: !hasWebGpu() },
          ]}
        />
      )}

      <SettingSelect
        settingKey="ttsThrottle"
        settingId="ttsThrottle"
        title={t('ttsSettings.throttle')}
        sub={t('ttsSettings.throttleHint')}
        options={[
          { value: 'auto', label: t('ttsSettings.throttleAuto') },
          { value: 'off', label: t('ttsSettings.throttleOff') },
          { value: 'balanced', label: t('ttsSettings.throttleBalanced') },
          { value: 'saver', label: t('ttsSettings.throttleSaver') },
        ]}
      />
    </>
  );
};

export default HdPerformance;
