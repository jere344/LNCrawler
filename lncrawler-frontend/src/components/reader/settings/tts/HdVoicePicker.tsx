import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  FormHelperText,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutlined';
import DownloadIcon from '@mui/icons-material/Download';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import { useTranslation } from 'react-i18next';
import { useReaderSettings } from '../../hooks/useReaderSettings';
import { updateReaderSetting } from '../../readerSettingsStore';
import { useSettingsContext } from '../settingsContext';
import {
  KOKORO_SIZE_MB,
  SUPERTONIC_SIZE_MB,
  type NeuralEngine,
  type NeuralOptions,
  type NeuralVoice,
} from '../../tts/voiceCatalog';
import { synthesize, wavToUrl } from '../../tts/neuralClient';
import { previewText, formatMb } from './ttsShared';
import type { useModelFamily } from './useModelFamily';
import { progressKey, type useNeuralModels } from '../useNeuralModels';

interface HdVoicePickerProps {
  lang: string;
  // The HD voices that read the language
  neuralVoices: NeuralVoice[];
  options: NeuralOptions;
  models: ReturnType<typeof useNeuralModels>;
  family: ReturnType<typeof useModelFamily>;
}

const FAMILY_NAME: Record<NeuralEngine, string> = { supertonic: 'Supertonic', kokoro: 'Kokoro', piper: 'Piper' };

// The HD voices of the language, grouped by model family, with their downloads and previews
const HdVoicePicker = ({ lang, neuralVoices, options, models, family }: HdVoicePickerProps) => {
  const { t } = useTranslation();
  const { ttsNeuralVoices, ttsRate, ttsVolume, ttsKokoroDevice } = useReaderSettings();
  // The model downloads are keyed by the voice's engine or id; progressKey picks the right one
  const { onBeforePreview } = useSettingsContext();
  const { downloaded, progress, storageBytes, neuralError, setNeuralError, downloadVoice, removeVoice, removeAll } = models;
  const { familyVoices, families, visibleFamily, setModelFamily } = family;
  const selectedId = ttsNeuralVoices[lang];
  const [previewing, setPreviewing] = useState<string | null>(null);

  const previewNeural = async (voice: NeuralVoice) => {
    onBeforePreview?.();
    setPreviewing(voice.id);
    setNeuralError(null);
    try {
      const { wav } = await synthesize(voice.id, options, previewText(lang)).promise;
      const url = wavToUrl(wav, ttsVolume);
      const audio = new Audio(url);
      audio.playbackRate = ttsRate;
      await new Promise<void>(resolve => {
        audio.onended = () => resolve();
        audio.onerror = () => resolve();
        audio.play().catch(() => resolve());
      });
      URL.revokeObjectURL(url);
    } catch (err) {
      setNeuralError(err instanceof Error ? err.message : String(err));
    } finally {
      setPreviewing(null);
    }
  };

  const voiceLabel = (voice: NeuralVoice) => {
    const gender = t(voice.gender === 'female' ? 'ttsSettings.female' : 'ttsSettings.male');
    if (voice.engine === 'supertonic') return { primary: `${gender} ${voice.id.slice(-1)}`, secondary: '' };
    return { primary: `${voice.name} · ${voice.accent}`, secondary: gender };
  };

  const neuralRow = (voice: NeuralVoice) => {
    const isSelected = selectedId === voice.id;
    const isDownloaded = downloaded.has(voice.id);
    const shared = voice.engine !== 'piper';
    const pct = progress[progressKey(voice)];
    const label = voiceLabel(voice);
    const previewButton = (
      <Tooltip title={t('ttsSettings.preview')}>
        <span>
          <IconButton
            size="small"
            aria-label={t('ttsSettings.preview')}
            disabled={!!previewing || !isDownloaded}
            onClick={e => { e.stopPropagation(); previewNeural(voice); }}
          >
            {previewing === voice.id ? <CircularProgress size={18} /> : <PlayCircleOutlineIcon fontSize="small" />}
          </IconButton>
        </span>
      </Tooltip>
    );
    return (
      <ListItemButton
        key={voice.id}
        selected={isSelected}
        onClick={() => updateReaderSetting('ttsNeuralVoices', { ...ttsNeuralVoices, [lang]: voice.id })}
        sx={{ borderRadius: 1, pr: 0.5 }}
        dense
      >
        {isSelected
          ? <CheckCircleIcon color="primary" fontSize="small" sx={{ mr: 1 }} />
          : <RadioButtonUncheckedIcon fontSize="small" sx={{ mr: 1, color: 'text.disabled' }} />}
        <ListItemText
          primary={label.primary}
          secondary={shared
            ? label.secondary || undefined
            : `${label.secondary} · ${isDownloaded ? t('ttsSettings.downloaded') : `${voice.sizeMb} MB`}`}
        />
        {shared ? previewButton : pct !== undefined ? (
          <CircularProgress size={22} variant={pct > 0 ? 'determinate' : 'indeterminate'} value={pct} sx={{ mx: 1 }} />
        ) : isDownloaded ? (
          <>
            {previewButton}
            <Tooltip title={t('ttsSettings.deleteVoice')}>
              <IconButton
                size="small"
                aria-label={t('ttsSettings.deleteVoice')}
                onClick={e => { e.stopPropagation(); removeVoice(voice); }}
              >
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </>
        ) : (
          <Tooltip title={t('ttsSettings.downloadVoice')}>
            <IconButton
              size="small"
              aria-label={t('ttsSettings.downloadVoice')}
              onClick={e => { e.stopPropagation(); downloadVoice(voice); }}
            >
              <DownloadIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </ListItemButton>
    );
  };

  /** Download/delete bar for engines whose voices share one model. */
  const sharedModelBar = (voices: NeuralVoice[], name: string, sizeMb: number) => {
    const first = voices[0];
    if (!first) return null;
    const isDownloaded = downloaded.has(first.id);
    const pct = progress[progressKey(first)];
    return (
      <Box
        sx={{
          display: 'flex', alignItems: 'center', gap: 1, mb: 1, px: 1.5, py: 1,
          borderRadius: 1, border: 1, borderColor: 'divider',
        }}
      >
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2">{t('ttsSettings.sharedModel', { name, size: sizeMb })}</Typography>
          <Typography variant="caption" color="text.secondary">
            {isDownloaded ? t('ttsSettings.downloaded') : t('ttsSettings.notDownloaded')}
          </Typography>
        </Box>
        {pct !== undefined ? (
          <CircularProgress size={24} variant={pct > 0 ? 'determinate' : 'indeterminate'} value={pct} />
        ) : isDownloaded ? (
          <Button size="small" color="error" startIcon={<DeleteOutlineIcon />} onClick={() => removeVoice(first)}>
            {t('common.delete')}
          </Button>
        ) : (
          <Button size="small" variant="contained" startIcon={<DownloadIcon />} onClick={() => downloadVoice(first)}>
            {t('tts.download')}
          </Button>
        )}
      </Box>
    );
  };

  return (
    <Box sx={{ mb: 2 }}>
      {neuralVoices.length === 0 ? (
        <Alert severity="info">
          {t('ttsSettings.noNeuralVoice', { language: t(`languages.${lang}`, { defaultValue: lang }) })}
        </Alert>
      ) : (
        <>
          {/* Only the families that read this language; one at a time. */}
          {families.length > 1 && (
            <ToggleButtonGroup
              exclusive
              fullWidth
              size="small"
              value={visibleFamily}
              onChange={(_, v) => v && setModelFamily(v)}
              sx={{ mb: 0.5 }}
            >
              {families.map(f => <ToggleButton key={f} value={f}>{FAMILY_NAME[f]}</ToggleButton>)}
            </ToggleButtonGroup>
          )}
          <FormHelperText sx={{ mb: 1 }}>
            {visibleFamily === 'supertonic'
              ? `${t('ttsSettings.supertonicGroup')}. ${t('ttsSettings.supertonicHint')}`
              : visibleFamily === 'kokoro'
                ? `${t('ttsSettings.kokoroGroup')}. ${t('ttsSettings.kokoroHint', { size: KOKORO_SIZE_MB[ttsKokoroDevice] })}`
                : `${t('ttsSettings.piperGroup')}. ${t('ttsSettings.piperHint')}`}
          </FormHelperText>

          {visibleFamily === 'supertonic' && sharedModelBar(familyVoices.supertonic, 'Supertonic', SUPERTONIC_SIZE_MB)}
          {visibleFamily === 'kokoro' && sharedModelBar(familyVoices.kokoro, 'Kokoro', KOKORO_SIZE_MB[ttsKokoroDevice])}

          <List dense disablePadding sx={{ mx: -1 }}>
            {familyVoices[visibleFamily].map(neuralRow)}
          </List>
        </>
      )}

      {neuralError && <Alert severity="error" sx={{ mt: 1 }}>{neuralError}</Alert>}

      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mt: 1.5, gap: 1 }}>
        <Typography variant="caption" color="text.secondary">
          {t('ttsSettings.storageUsed', { size: formatMb(storageBytes) })}
        </Typography>
        <Button size="small" color="error" onClick={removeAll} disabled={storageBytes === 0}>
          {t('ttsSettings.deleteAll')}
        </Button>
      </Box>
    </Box>
  );
};

export default HdVoicePicker;
