import { useEffect, useMemo, useState } from 'react';
import { Alert, Box, CircularProgress, FormControl, IconButton, ListItemText, MenuItem, Select, Tooltip } from '@mui/material';
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutlined';
import { useTranslation } from 'react-i18next';
import { useReaderSettings } from '../../hooks/useReaderSettings';
import { updateReaderSetting } from '../../readerSettingsStore';
import { useSettingsContext } from '../settingsContext';
import { getBrowserVoices, isBrowserSpeechSupported, pickBrowserVoice, speak, voicesForLang } from '../../tts/browserSpeech';
import { previewText } from './ttsShared';

interface BrowserVoicePickerProps {
  lang: string;
}

// The device voices for the language, with a preview of the one picked
const BrowserVoicePicker = ({ lang }: BrowserVoicePickerProps) => {
  const { t } = useTranslation();
  const { ttsBrowserVoices, ttsRate, ttsPitch, ttsVolume } = useReaderSettings();
  const { onBeforePreview } = useSettingsContext();
  const [browserVoices, setBrowserVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [previewing, setPreviewing] = useState(false);
  useEffect(() => {
    let cancelled = false;
    getBrowserVoices().then(v => { if (!cancelled) setBrowserVoices(v); });
    return () => { cancelled = true; };
  }, []);
  const langBrowserVoices = useMemo(() => voicesForLang(browserVoices, lang), [browserVoices, lang]);
  const pickedUri = ttsBrowserVoices[lang];
  const langName = t(`languages.${lang}`, { defaultValue: lang });

  const preview = async () => {
    onBeforePreview?.();
    setPreviewing(true);
    try {
      await speak(previewText(lang), {
        voice: pickBrowserVoice(browserVoices, lang, pickedUri),
        lang,
        rate: ttsRate,
        pitch: ttsPitch,
        volume: ttsVolume,
      });
    } catch (err) {
      console.error('Voice preview failed:', err);
    } finally {
      setPreviewing(false);
    }
  };

  if (!isBrowserSpeechSupported()) {
    return <Alert severity="warning" sx={{ mb: 2 }}>{t('ttsSettings.browserUnsupported')}</Alert>;
  }

  return (
    <Box sx={{ mb: 2 }}>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <FormControl fullWidth size="small">
          <Select
            value={langBrowserVoices.some(v => v.voiceURI === pickedUri) ? pickedUri : ''}
            displayEmpty
            onChange={e => {
              const next = { ...ttsBrowserVoices };
              if (e.target.value) next[lang] = e.target.value;
              else delete next[lang];
              updateReaderSetting('ttsBrowserVoices', next);
            }}
          >
            <MenuItem value="">{t('ttsSettings.voiceAuto')}</MenuItem>
            {langBrowserVoices.map(v => (
              <MenuItem key={v.voiceURI} value={v.voiceURI}>
                <ListItemText
                  primary={v.name}
                  secondary={`${v.lang}${v.localService ? '' : ` · ${t('ttsSettings.online')}`}`}
                  sx={{ my: 0 }}
                />
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Tooltip title={t('ttsSettings.preview')}>
          <span>
            <IconButton aria-label={t('ttsSettings.preview')} onClick={preview} disabled={previewing}>
              {previewing ? <CircularProgress size={20} /> : <PlayCircleOutlineIcon />}
            </IconButton>
          </span>
        </Tooltip>
      </Box>
      {langBrowserVoices.length === 0 && browserVoices.length > 0 && (
        <Alert severity="info" sx={{ mt: 1 }}>
          {t('ttsSettings.noBrowserVoice', { language: langName })}
        </Alert>
      )}
      {browserVoices.length === 0 && (
        <Alert severity="info" sx={{ mt: 1 }}>{t('ttsSettings.noBrowserVoices')}</Alert>
      )}
    </Box>
  );
};

export default BrowserVoicePicker;
