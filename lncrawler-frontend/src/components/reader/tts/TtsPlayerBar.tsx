import React, { useEffect, useState } from 'react';
import {
  Box,
  Button,
  IconButton,
  LinearProgress,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Paper,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import SkipNextIcon from '@mui/icons-material/SkipNext';
import SkipPreviousIcon from '@mui/icons-material/SkipPrevious';
import FastForwardIcon from '@mui/icons-material/FastForward';
import FastRewindIcon from '@mui/icons-material/FastRewind';
import BedtimeIcon from '@mui/icons-material/Bedtime';
import BedtimeOutlinedIcon from '@mui/icons-material/BedtimeOutlined';
import TuneIcon from '@mui/icons-material/Tune';
import CloseIcon from '@mui/icons-material/Close';
import CheckIcon from '@mui/icons-material/Check';
import { useTranslation } from 'react-i18next';
import type { TtsPlayer } from './useTtsPlayer';
import { TTS_RATE_STEPS } from './ttsTypes';

interface TtsPlayerBarProps {
  tts: TtsPlayer;
  rate: number;
  onRateChange: (rate: number) => void;
  onOpenSettings: () => void;
  chapterTitle: string;
}

const SLEEP_MINUTES = [10, 15, 30, 45, 60, 90];

const formatRate = (r: number) => `${Number(r.toFixed(2))}×`;

const TtsPlayerBar: React.FC<TtsPlayerBarProps> = ({
  tts,
  rate,
  onRateChange,
  onOpenSettings,
  chapterTitle,
}) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [speedAnchor, setSpeedAnchor] = useState<HTMLElement | null>(null);
  const [sleepAnchor, setSleepAnchor] = useState<HTMLElement | null>(null);
  const [now, setNow] = useState(() => Date.now());

  // Refresh the sleep timer countdown.
  useEffect(() => {
    if (tts.sleepTimer.mode !== 'time') return;
    const id = window.setInterval(() => setNow(Date.now()), 15000);
    return () => window.clearInterval(id);
  }, [tts.sleepTimer]);

  if (!tts.open) return null;

  const isPlaying = tts.status === 'playing' || tts.status === 'preparing';
  const minutesLeft = tts.sleepTimer.mode === 'time'
    ? Math.max(1, Math.ceil((tts.sleepTimer.endsAt - now) / 60000))
    : 0;

  const statusLine = (() => {
    if (tts.status === 'preparing') {
      if (tts.download && tts.download.total > 0) {
        return t('tts.downloading', { percent: Math.floor((tts.download.loaded / tts.download.total) * 100) });
      }
      return tts.chunkIndex < 0 && !tts.download ? t('tts.loadingChapter') : t('tts.preparing');
    }
    if (tts.chunkIndex >= 0 && tts.paragraph === 0 && (tts.status === 'playing' || tts.status === 'paused')) {
      return t('tts.readingTitle');
    }
    if (tts.paragraphCount > 0 && tts.paragraph > 0) {
      return t('tts.paragraphOf', { current: tts.paragraph, total: tts.paragraphCount });
    }
    return t('tts.ready');
  })();

  const errorMessage = (() => {
    switch (tts.errorKind) {
      case 'unsupported': return t('tts.errorUnsupported');
      case 'noVoice': return t('tts.errorNoVoice');
      case 'neuralFailed': return t('tts.errorNeural');
      case 'noContent': return t('tts.errorNoContent');
      default: return '';
    }
  })();

  const downloadPercent = tts.download && tts.download.total > 0
    ? (tts.download.loaded / tts.download.total) * 100
    : null;

  const iconButton = (
    label: string,
    icon: React.ReactNode,
    onClick: (e: React.MouseEvent<HTMLElement>) => void,
    disabled = false,
  ) => (
    <Tooltip title={label} disableInteractive>
      <span>
        <IconButton aria-label={label} onClick={onClick} disabled={disabled}>
          {icon}
        </IconButton>
      </span>
    </Tooltip>
  );

  const canNavigate = tts.status !== 'needsDownload' && tts.status !== 'error';

  let body: React.ReactNode;
  if (tts.status === 'needsDownload' && tts.neuralVoice) {
    body = (
      <Box sx={{ px: 2, py: 1.5 }}>
        <Typography variant="body2" sx={{ fontWeight: 500 }}>
          {t('tts.needsDownloadTitle', { voice: tts.neuralVoice.name, size: tts.neuralVoice.sizeMb })}
        </Typography>
        <Typography variant="caption" color="text.secondary" component="p" sx={{ mb: 1 }}>
          {t('tts.needsDownloadHint')}
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <Button size="small" onClick={tts.switchToDeviceVoices}>{t('tts.useDeviceVoice')}</Button>
          <Button size="small" variant="contained" onClick={tts.confirmDownload}>{t('tts.download')}</Button>
        </Box>
      </Box>
    );
  } else if (tts.status === 'error') {
    body = (
      <Box sx={{ px: 2, py: 1.5 }}>
        <Typography variant="body2" color="error" sx={{ fontWeight: 500 }}>{errorMessage}</Typography>
        {tts.errorDetail && (
          <Typography variant="caption" color="text.secondary" component="p" sx={{ wordBreak: 'break-word' }}>
            {tts.errorDetail}
          </Typography>
        )}
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', justifyContent: 'flex-end', mt: 1 }}>
          {tts.errorKind === 'neuralFailed' && (
            <Button size="small" onClick={tts.switchToDeviceVoices}>{t('tts.useDeviceVoice')}</Button>
          )}
          {tts.errorKind === 'noVoice' && tts.engine === 'browser' && (
            <Button size="small" onClick={tts.switchToHdVoices}>{t('tts.useHdVoice')}</Button>
          )}
          <Button size="small" variant="contained" onClick={tts.play}>{t('tts.retry')}</Button>
        </Box>
      </Box>
    );
  } else {
    body = (
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: { xs: 0.5, sm: 1 }, py: 0.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          {iconButton(
            tts.sleepTimer.mode === 'off' ? t('tts.sleepTimer') : t('tts.sleepTimerOn'),
            <Box sx={{ position: 'relative', display: 'flex' }}>
              {tts.sleepTimer.mode === 'off' ? <BedtimeOutlinedIcon /> : <BedtimeIcon color="primary" />}
              {tts.sleepTimer.mode === 'time' && (
                <Typography
                  component="span"
                  sx={{ position: 'absolute', bottom: -8, right: -10, fontSize: 10, fontWeight: 700, color: 'primary.main' }}
                >
                  {minutesLeft}′
                </Typography>
              )}
            </Box>,
            e => setSleepAnchor(e.currentTarget),
          )}
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 0, sm: 0.5 } }}>
          {iconButton(t('tts.prevParagraph'), <SkipPreviousIcon />, () => tts.skipBlock(-1), !canNavigate)}
          {!isMobile && iconButton(t('tts.prevSentence'), <FastRewindIcon />, () => tts.skipChunk(-1), !canNavigate)}
          <Tooltip title={isPlaying ? t('tts.pause') : t('tts.play')} disableInteractive>
            <IconButton
              aria-label={isPlaying ? t('tts.pause') : t('tts.play')}
              onClick={tts.toggle}
              sx={{
                mx: 0.5,
                width: 52,
                height: 52,
                bgcolor: 'primary.main',
                color: 'primary.contrastText',
                '&:hover': { bgcolor: 'primary.dark' },
              }}
            >
              {isPlaying ? <PauseIcon fontSize="large" /> : <PlayArrowIcon fontSize="large" />}
            </IconButton>
          </Tooltip>
          {!isMobile && iconButton(t('tts.nextSentence'), <FastForwardIcon />, () => tts.skipChunk(1), !canNavigate)}
          {iconButton(t('tts.nextParagraph'), <SkipNextIcon />, () => tts.skipBlock(1), !canNavigate)}
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <Tooltip title={t('tts.speed')} disableInteractive>
            <Button
              aria-label={t('tts.speed')}
              onClick={e => setSpeedAnchor(e.currentTarget)}
              size="small"
              sx={{ minWidth: 48, px: 0.5, fontWeight: 700, color: 'text.primary' }}
            >
              {formatRate(rate)}
            </Button>
          </Tooltip>
          {!isMobile && iconButton(t('tts.settings'), <TuneIcon />, onOpenSettings)}
        </Box>
      </Box>
    );
  }

  return (
    <Paper
      elevation={8}
      role="region"
      aria-label={t('tts.player')}
      sx={{
        position: 'fixed',
        zIndex: theme.zIndex.appBar,
        overflow: 'hidden',
        ...(isMobile
          ? {
              left: 0,
              right: 0,
              bottom: 0,
              borderRadius: '16px 16px 0 0',
              pb: 'env(safe-area-inset-bottom)',
            }
          : {
              left: '50%',
              bottom: 16,
              transform: 'translateX(-50%)',
              width: 'min(640px, calc(100% - 32px))',
              borderRadius: 3,
            }),
      }}
    >
      <LinearProgress
        variant={tts.status === 'preparing' && downloadPercent === null ? 'indeterminate' : 'determinate'}
        value={downloadPercent ?? tts.progress * 100}
        sx={{ height: 3 }}
      />

      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, pl: 2, pr: 0.5, pt: 0.5 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2" noWrap sx={{ fontWeight: 500 }}>{chapterTitle}</Typography>
          <Typography variant="caption" color="text.secondary" noWrap component="p">
            {statusLine}
            {' · '}
            {tts.engine === 'neural' && tts.neuralVoice
              ? t('tts.hdVoiceBadge', { voice: tts.neuralVoice.name })
              : t('tts.deviceVoiceBadge')}
          </Typography>
        </Box>
        {isMobile && iconButton(t('tts.settings'), <TuneIcon fontSize="small" />, onOpenSettings)}
        {iconButton(t('tts.close'), <CloseIcon fontSize="small" />, tts.close)}
      </Box>

      {body}

      <Menu
        anchorEl={speedAnchor}
        open={!!speedAnchor}
        onClose={() => setSpeedAnchor(null)}
        anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
        transformOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        {TTS_RATE_STEPS.map(step => (
          <MenuItem
            key={step}
            selected={Math.abs(step - rate) < 0.001}
            onClick={() => { onRateChange(step); setSpeedAnchor(null); }}
            dense
          >
            {formatRate(step)}
          </MenuItem>
        ))}
      </Menu>

      <Menu
        anchorEl={sleepAnchor}
        open={!!sleepAnchor}
        onClose={() => setSleepAnchor(null)}
        anchorOrigin={{ vertical: 'top', horizontal: 'left' }}
        transformOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      >
        {[
          { key: 'off', label: t('tts.sleepOff'), active: tts.sleepTimer.mode === 'off', set: () => tts.setSleepTimer({ mode: 'off' }) },
          { key: 'chapter', label: t('tts.sleepEndOfChapter'), active: tts.sleepTimer.mode === 'chapter', set: () => tts.setSleepTimer({ mode: 'chapter' }) },
          ...SLEEP_MINUTES.map(m => ({
            key: String(m),
            label: t('tts.sleepMinutes', { minutes: m }),
            active: false,
            set: () => tts.setSleepTimer({ mode: 'time', endsAt: Date.now() + m * 60000 }),
          })),
        ].map(item => (
          <MenuItem key={item.key} dense onClick={() => { item.set(); setSleepAnchor(null); }}>
            <ListItemIcon>{item.active && <CheckIcon fontSize="small" />}</ListItemIcon>
            <ListItemText>{item.label}</ListItemText>
          </MenuItem>
        ))}
        {tts.sleepTimer.mode === 'time' && (
          <MenuItem disabled dense>
            <ListItemIcon />
            <ListItemText>{t('tts.sleepRemaining', { minutes: minutesLeft })}</ListItemText>
          </MenuItem>
        )}
      </Menu>
    </Paper>
  );
};

export default TtsPlayerBar;
