import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  FormControl,
  FormControlLabel,
  FormHelperText,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  MenuItem,
  Select,
  Slider,
  Switch,
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
import PhoneAndroidIcon from '@mui/icons-material/PhoneAndroid';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import HeadphonesIcon from '@mui/icons-material/Headphones';
import { useTranslation } from 'react-i18next';
import { availableLanguages } from '@utils/Misc';
import { neuralOptions, neuralOptionsKey, type TtsPrefs } from '../tts/ttsTypes';
import {
  KOKORO_SIZE_MB,
  PREVIEW_TEXT,
  SUPERTONIC_LICENSE_URL,
  SUPERTONIC_SIZE_MB,
  SUPERTONIC_STEPS,
  getNeuralVoicesForLang,
  resolveNeuralVoice,
  type NeuralEngine,
  type NeuralVoice,
} from '../tts/voiceCatalog';
import {
  getBrowserVoices,
  isBrowserSpeechSupported,
  pickBrowserVoice,
  speak,
  voicesForLang,
} from '../tts/browserSpeech';
import {
  isNeuralSupported,
  synthesize,
  wavToUrl,
} from '../tts/neuralClient';
import { progressKey, useNeuralModels } from './useNeuralModels';

interface TtsSettingsProps {
  prefs: TtsPrefs;
  onChange: <K extends keyof TtsPrefs>(key: K, value: TtsPrefs[K]) => void;
  /** Language of the novel being read (used when ttsLanguage is ''). */
  novelLanguage: string;
  /** Called before a voice preview plays, so the player can pause. */
  onBeforePreview?: () => void;
  /** The current chapter has a narrated audiobook recording. */
  hasNarration?: boolean;
}

const formatMb = (bytes: number) => `${Math.round(bytes / 1e6)} MB`;
const hasWebGpu = () => typeof navigator !== 'undefined' && 'gpu' in navigator;

/**
 * Text-to-speech section of the reader settings drawer.
 */
const TtsSettings: React.FC<TtsSettingsProps> = ({ prefs, onChange, novelLanguage, onBeforePreview, hasNarration = false }) => {
  const { t } = useTranslation();
  const lang = prefs.ttsLanguage || novelLanguage;
  const neuralSupported = isNeuralSupported();
  // Narrated without a recording for this chapter: client TTS reads it with the browser engine.
  const selectedEngine = prefs.ttsEngine === 'narrated' && !hasNarration ? 'browser' : prefs.ttsEngine;
  const clientEngine = prefs.ttsEngine === 'neural' ? 'neural' : 'browser';

  // ---- Device voices ------------------------------------------------------
  const [browserVoices, setBrowserVoices] = useState<SpeechSynthesisVoice[]>([]);
  useEffect(() => {
    let cancelled = false;
    getBrowserVoices().then(v => { if (!cancelled) setBrowserVoices(v); });
    return () => { cancelled = true; };
  }, []);
  const langBrowserVoices = useMemo(() => voicesForLang(browserVoices, lang), [browserVoices, lang]);

  // ---- HD voices ----------------------------------------------------------
  const neuralVoices = useMemo(() => getNeuralVoicesForLang(lang), [lang]);
  const selectedNeural = resolveNeuralVoice(lang, prefs.ttsNeuralVoices);
  const optionsKey = neuralOptionsKey(neuralOptions(prefs));
  // eslint-disable-next-line react-hooks/exhaustive-deps -- recomputed from its key
  const options = useMemo(() => neuralOptions(prefs), [optionsKey]);
  const [previewing, setPreviewing] = useState<string | null>(null);
  // Which model family's voices are listed; opens on the selected voice's.
  const [modelFamily, setModelFamily] = useState<NeuralEngine>(selectedNeural?.engine ?? 'supertonic');
  useEffect(() => {
    setModelFamily(resolveNeuralVoice(lang, prefs.ttsNeuralVoices)?.engine ?? 'supertonic');
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-sync only when the language changes
  }, [lang]);

  const { downloaded, progress, storageBytes, neuralError, setNeuralError, downloadVoice, removeVoice, removeAll } = useNeuralModels({
    ttsEngine: prefs.ttsEngine,
    neuralSupported,
    neuralVoices,
    options,
    selectedNeuralId: selectedNeural?.id,
  });

  // ---- Previews -----------------------------------------------------------
  const sample = PREVIEW_TEXT[lang] ?? PREVIEW_TEXT.en;

  const previewBrowser = async () => {
    onBeforePreview?.();
    setPreviewing('browser');
    try {
      await speak(sample, {
        voice: pickBrowserVoice(browserVoices, lang, prefs.ttsBrowserVoices[lang]),
        lang,
        rate: prefs.ttsRate,
        pitch: prefs.ttsPitch,
        volume: prefs.ttsVolume,
      });
    } catch (err) {
      console.error('Voice preview failed:', err);
    } finally {
      setPreviewing(null);
    }
  };

  const previewNeural = async (voice: NeuralVoice) => {
    onBeforePreview?.();
    setPreviewing(voice.id);
    setNeuralError(null);
    try {
      const { wav } = await synthesize(voice.id, options, sample).promise;
      const url = wavToUrl(wav, prefs.ttsVolume);
      const audio = new Audio(url);
      audio.playbackRate = prefs.ttsRate;
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

  // ---- Render helpers -----------------------------------------------------
  const sliderRow = (
    label: string,
    value: number,
    display: string,
    min: number,
    max: number,
    step: number,
    onValue: (v: number) => void,
    disabled = false,
  ) => (
    <Box sx={{ mb: 1 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
        <Typography variant="body2" color={disabled ? 'text.disabled' : undefined}>{label}</Typography>
        <Typography variant="body2" color="text.secondary">{display}</Typography>
      </Box>
      <Slider
        size="small"
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onChange={(_, v) => onValue(v as number)}
        aria-label={label}
      />
    </Box>
  );

  const switchRow = (label: string, checked: boolean, onValue: (v: boolean) => void, hint?: string) => (
    <FormControl fullWidth sx={{ mb: 1 }}>
      <FormControlLabel
        control={<Switch checked={checked} onChange={e => onValue(e.target.checked)} />}
        label={<Typography variant="body2">{label}</Typography>}
      />
      {hint && <FormHelperText sx={{ mt: -0.5 }}>{hint}</FormHelperText>}
    </FormControl>
  );

  const voiceLabel = (voice: NeuralVoice) => {
    const gender = t(voice.gender === 'female' ? 'ttsSettings.female' : 'ttsSettings.male');
    if (voice.engine === 'supertonic') return { primary: `${gender} ${voice.id.slice(-1)}`, secondary: '' };
    return { primary: `${voice.name} · ${voice.accent}`, secondary: gender };
  };

  const neuralRow = (voice: NeuralVoice) => {
    const isSelected = selectedNeural?.id === voice.id;
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
        onClick={() => onChange('ttsNeuralVoices', { ...prefs.ttsNeuralVoices, [lang]: voice.id })}
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

  const familyVoices: Record<NeuralEngine, NeuralVoice[]> = {
    supertonic: neuralVoices.filter(v => v.engine === 'supertonic'),
    kokoro: neuralVoices.filter(v => v.engine === 'kokoro'),
    piper: neuralVoices.filter(v => v.engine === 'piper'),
  };
  const families = (['supertonic', 'kokoro', 'piper'] as const).filter(f => familyVoices[f].length > 0);
  const visibleFamily: NeuralEngine = families.includes(modelFamily) ? modelFamily : families[0] ?? 'piper';
  const familyName: Record<NeuralEngine, string> = { supertonic: 'Supertonic', kokoro: 'Kokoro', piper: 'Piper' };

  return (
    <Box>
      {/* Engine */}
      <Typography variant="body2" sx={{ mb: 1 }}>{t('ttsSettings.engine')}</Typography>
      <ToggleButtonGroup
        exclusive
        fullWidth
        size="small"
        value={selectedEngine}
        onChange={(_, v) => v && onChange('ttsEngine', v)}
        sx={{ mb: 0.5 }}
      >
        <ToggleButton value="browser" sx={{ gap: 0.5 }}>
          <PhoneAndroidIcon fontSize="small" /> {t('ttsSettings.engineBrowser')}
        </ToggleButton>
        <ToggleButton value="neural" disabled={!neuralSupported} sx={{ gap: 0.5 }}>
          <AutoAwesomeIcon fontSize="small" /> {t('ttsSettings.engineNeural')}
        </ToggleButton>
        {hasNarration && (
          <ToggleButton value="narrated" sx={{ gap: 0.5 }}>
            <HeadphonesIcon fontSize="small" /> {t('ttsSettings.engineNarrated')}
          </ToggleButton>
        )}
      </ToggleButtonGroup>
      <FormHelperText sx={{ mb: 2 }}>
        {selectedEngine === 'narrated'
          ? t('ttsSettings.engineNarratedHint')
          : selectedEngine === 'browser' ? t('ttsSettings.engineBrowserHint') : t('ttsSettings.engineNeuralHint')}
      </FormHelperText>

      {/* Language */}
      <Typography variant="body2" sx={{ mb: 1 }}>{t('ttsSettings.language')}</Typography>
      <FormControl fullWidth size="small">
        <Select
          value={prefs.ttsLanguage}
          displayEmpty
          onChange={e => onChange('ttsLanguage', e.target.value)}
        >
          <MenuItem value="">
            {t('ttsSettings.languageAuto', { language: t(`languages.${novelLanguage}`, { defaultValue: novelLanguage }) })}
          </MenuItem>
          {availableLanguages.map(code => (
            <MenuItem key={code} value={code}>{t(`languages.${code}`)}</MenuItem>
          ))}
        </Select>
        <FormHelperText>{t('ttsSettings.languageHint')}</FormHelperText>
      </FormControl>

      {/* Voice */}
      <Typography variant="body2" sx={{ mt: 2, mb: 1 }}>
        {t('ttsSettings.voiceFor', { language: t(`languages.${lang}`, { defaultValue: lang }) })}
      </Typography>

      {clientEngine === 'browser' && (
        !isBrowserSpeechSupported() ? (
          <Alert severity="warning" sx={{ mb: 2 }}>{t('ttsSettings.browserUnsupported')}</Alert>
        ) : (
          <Box sx={{ mb: 2 }}>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
              <FormControl fullWidth size="small">
                <Select
                  value={langBrowserVoices.some(v => v.voiceURI === prefs.ttsBrowserVoices[lang]) ? prefs.ttsBrowserVoices[lang] : ''}
                  displayEmpty
                  onChange={e => {
                    const next = { ...prefs.ttsBrowserVoices };
                    if (e.target.value) next[lang] = e.target.value;
                    else delete next[lang];
                    onChange('ttsBrowserVoices', next);
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
                  <IconButton aria-label={t('ttsSettings.preview')} onClick={previewBrowser} disabled={!!previewing}>
                    {previewing === 'browser' ? <CircularProgress size={20} /> : <PlayCircleOutlineIcon />}
                  </IconButton>
                </span>
              </Tooltip>
            </Box>
            {langBrowserVoices.length === 0 && browserVoices.length > 0 && (
              <Alert severity="info" sx={{ mt: 1 }}>
                {t('ttsSettings.noBrowserVoice', { language: t(`languages.${lang}`, { defaultValue: lang }) })}
              </Alert>
            )}
            {browserVoices.length === 0 && (
              <Alert severity="info" sx={{ mt: 1 }}>{t('ttsSettings.noBrowserVoices')}</Alert>
            )}
          </Box>
        )
      )}

      {clientEngine === 'neural' && (
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
                  {families.map(f => <ToggleButton key={f} value={f}>{familyName[f]}</ToggleButton>)}
                </ToggleButtonGroup>
              )}
              <FormHelperText sx={{ mb: 1 }}>
                {visibleFamily === 'supertonic'
                  ? `${t('ttsSettings.supertonicGroup')}. ${t('ttsSettings.supertonicHint')}`
                  : visibleFamily === 'kokoro'
                    ? `${t('ttsSettings.kokoroGroup')}. ${t('ttsSettings.kokoroHint', { size: KOKORO_SIZE_MB[prefs.ttsKokoroDevice] })}`
                    : `${t('ttsSettings.piperGroup')}. ${t('ttsSettings.piperHint')}`}
              </FormHelperText>

              {visibleFamily === 'supertonic' && sharedModelBar(familyVoices.supertonic, 'Supertonic', SUPERTONIC_SIZE_MB)}
              {visibleFamily === 'kokoro' && sharedModelBar(familyVoices.kokoro, 'Kokoro', KOKORO_SIZE_MB[prefs.ttsKokoroDevice])}

              <List dense disablePadding sx={{ mx: -1 }}>
                {familyVoices[visibleFamily].map(neuralRow)}
              </List>

              {visibleFamily === 'supertonic' && (
                <>
                  <Typography variant="body2" sx={{ mt: 2, mb: 1 }}>{t('ttsSettings.quality')}</Typography>
                  <ToggleButtonGroup
                    exclusive
                    fullWidth
                    size="small"
                    value={prefs.ttsSupertonicSteps}
                    onChange={(_, v) => v && onChange('ttsSupertonicSteps', v)}
                  >
                    <ToggleButton value={SUPERTONIC_STEPS.fast}>{t('ttsSettings.qualityFast')}</ToggleButton>
                    <ToggleButton value={SUPERTONIC_STEPS.balanced}>{t('ttsSettings.qualityBalanced')}</ToggleButton>
                    <ToggleButton value={SUPERTONIC_STEPS.best}>{t('ttsSettings.qualityBest')}</ToggleButton>
                  </ToggleButtonGroup>
                  <FormHelperText sx={{ mb: 2 }}>{t('ttsSettings.qualityHint')}</FormHelperText>

                  <FormControl fullWidth size="small">
                    <Typography variant="body2" sx={{ mb: 1 }}>{t('ttsSettings.supertonicDevice')}</Typography>
                    <Select
                      value={prefs.ttsSupertonicDevice}
                      onChange={e => onChange('ttsSupertonicDevice', e.target.value as TtsPrefs['ttsSupertonicDevice'])}
                    >
                      <MenuItem value="auto">{t('ttsSettings.deviceAuto')}</MenuItem>
                      <MenuItem value="wasm">{t('ttsSettings.deviceCpuShort')}</MenuItem>
                      <MenuItem value="webgpu" disabled={!hasWebGpu()}>{t('ttsSettings.deviceGpuShort')}</MenuItem>
                    </Select>
                  </FormControl>
                  <Typography variant="caption" component="p" color="text.secondary" sx={{ mt: 1 }}>
                    <a href={SUPERTONIC_LICENSE_URL} target="_blank" rel="noopener noreferrer" style={{ color: 'inherit' }}>
                      {t('ttsSettings.modelLicense')}
                    </a>
                  </Typography>
                </>
              )}

              {visibleFamily === 'kokoro' && (
                <FormControl fullWidth size="small" sx={{ mt: 2 }}>
                  <Typography variant="body2" sx={{ mb: 1 }}>{t('ttsSettings.kokoroDevice')}</Typography>
                  <Select
                    value={prefs.ttsKokoroDevice}
                    onChange={e => onChange('ttsKokoroDevice', e.target.value as TtsPrefs['ttsKokoroDevice'])}
                  >
                    <MenuItem value="wasm">{t('ttsSettings.deviceCpu', { size: KOKORO_SIZE_MB.wasm })}</MenuItem>
                    <MenuItem value="webgpu" disabled={!hasWebGpu()}>
                      {t('ttsSettings.deviceGpu', { size: KOKORO_SIZE_MB.webgpu })}
                    </MenuItem>
                  </Select>
                  <FormHelperText>{t('ttsSettings.kokoroDeviceHint')}</FormHelperText>
                </FormControl>
              )}

              <FormControl fullWidth size="small" sx={{ mt: 2 }}>
                <Typography variant="body2" sx={{ mb: 1 }}>{t('ttsSettings.throttle')}</Typography>
                <Select
                  value={prefs.ttsThrottle}
                  onChange={e => onChange('ttsThrottle', e.target.value as TtsPrefs['ttsThrottle'])}
                >
                  <MenuItem value="auto">{t('ttsSettings.throttleAuto')}</MenuItem>
                  <MenuItem value="off">{t('ttsSettings.throttleOff')}</MenuItem>
                  <MenuItem value="balanced">{t('ttsSettings.throttleBalanced')}</MenuItem>
                  <MenuItem value="saver">{t('ttsSettings.throttleSaver')}</MenuItem>
                </Select>
                <FormHelperText>{t('ttsSettings.throttleHint')}</FormHelperText>
              </FormControl>
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
      )}

      {/* Playback */}
      <Typography variant="subtitle2" sx={{ mt: 1, mb: 1 }}>{t('ttsSettings.playback')}</Typography>
      {sliderRow(t('ttsSettings.speed'), prefs.ttsRate, `${prefs.ttsRate.toFixed(2)}×`, 0.5, 3, 0.05, v => onChange('ttsRate', v))}
      {sliderRow(
        t('ttsSettings.pitch'), prefs.ttsPitch, prefs.ttsPitch.toFixed(2), 0.5, 2, 0.05,
        v => onChange('ttsPitch', v), clientEngine === 'neural',
      )}
      {sliderRow(
        t('ttsSettings.volume'), prefs.ttsVolume, `${Math.round(prefs.ttsVolume * 100)}%`, 0, 1, 0.05,
        v => onChange('ttsVolume', v), clientEngine === 'browser',
      )}
      {clientEngine === 'browser' && (
        <FormHelperText sx={{ mt: -1, mb: 1 }}>{t('ttsSettings.volumeBrowserHint')}</FormHelperText>
      )}
      {sliderRow(
        t('ttsSettings.paragraphPause'), prefs.ttsParagraphPause,
        t('ttsSettings.milliseconds', { value: prefs.ttsParagraphPause }), 0, 2000, 50,
        v => onChange('ttsParagraphPause', v),
      )}

      {/* Reading */}
      <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>{t('ttsSettings.reading')}</Typography>
      <Typography variant="body2" sx={{ mb: 1 }}>{t('ttsSettings.highlight')}</Typography>
      <FormControl fullWidth size="small" sx={{ mb: 2 }}>
        <Select
          value={prefs.ttsHighlight}
          onChange={e => onChange('ttsHighlight', e.target.value as TtsPrefs['ttsHighlight'])}
        >
          <MenuItem value="sentence">{t('ttsSettings.highlightSentence')}</MenuItem>
          <MenuItem value="paragraph">{t('ttsSettings.highlightParagraph')}</MenuItem>
          <MenuItem value="none">{t('ttsSettings.highlightNone')}</MenuItem>
        </Select>
      </FormControl>
      {switchRow(t('ttsSettings.autoScroll'), prefs.ttsAutoScroll, v => onChange('ttsAutoScroll', v), t('ttsSettings.autoScrollHint'))}
      {switchRow(t('ttsSettings.autoNextChapter'), prefs.ttsAutoNextChapter, v => onChange('ttsAutoNextChapter', v))}
      {switchRow(t('ttsSettings.readTitle'), prefs.ttsReadTitle, v => onChange('ttsReadTitle', v))}
      {switchRow(t('ttsSettings.skipNotes'), prefs.ttsSkipNotes, v => onChange('ttsSkipNotes', v), t('ttsSettings.skipNotesHint'))}
      {switchRow(t('ttsSettings.tapToSeek'), prefs.ttsTapToSeek, v => onChange('ttsTapToSeek', v), t('ttsSettings.tapToSeekHint'))}
      {switchRow(t('ttsSettings.keepScreenOn'), prefs.ttsKeepScreenOn, v => onChange('ttsKeepScreenOn', v), t('ttsSettings.keepScreenOnHint'))}
    </Box>
  );
};

export default TtsSettings;
