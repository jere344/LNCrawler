import React from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { Box, IconButton, Paper, Tooltip, Typography, useMediaQuery, useTheme } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import Forward30Icon from '@mui/icons-material/Forward30';
import ReplayIcon from '@mui/icons-material/Replay';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';
import CloseIcon from '@mui/icons-material/Close';
import { useTranslation } from 'react-i18next';
import { useAudioPlayer, useAudioPlayerTime } from '@context/AudioPlayerContext';
import { useAdultContent } from '@context/AdultContentContext';
import { audiobookRevealKey } from '@utils/audiobook';
import { formatClock } from '@utils/duration';

// Fixed bar at the bottom of the screen, under the app bar. Hidden when nothing is loaded or a reader bar takes its place.
const MiniPlayer: React.FC = () => {
  const { t } = useTranslation();
  const theme = useTheme();
  const reducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)');
  const player = useAudioPlayer();
  const { position, duration } = useAudioPlayerTime();
  const { isBlurred, revealHandler } = useAdultContent();
  const { book, chapter, status, suppressed } = player;

  if (!book || !chapter || suppressed) return null;

  const playing = status === 'playing';
  const loading = status === 'loading';
  const failed = status === 'error';
  const percent = duration > 0 ? Math.min(100, (position / duration) * 100) : 0;
  const cover = book.cover_jpg_url ?? book.cover_url;
  const revealKey = audiobookRevealKey(book.slug, book.language);
  const blurred = isBlurred(book.is_adult, revealKey);

  return (
    <Paper
      elevation={6}
      role="region"
      aria-label={t('audioPlayer.nowPlaying')}
      sx={{
        position: 'fixed',
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: theme.zIndex.appBar - 1,
        // On phones the bar also clears the home indicator; the App spacer adds the same inset.
        height: { xs: 'calc(64px + env(safe-area-inset-bottom))', sm: 64 },
        pb: { xs: 'env(safe-area-inset-bottom)', sm: 0 },
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        px: { xs: 1, sm: 2 },
        borderRadius: 0,
      }}
    >
      <Box
        component="img"
        src={cover ?? undefined}
        alt=""
        onClick={blurred ? revealHandler(revealKey) : () => player.expand(true)}
        sx={{
          width: 40,
          height: 40,
          borderRadius: 1,
          objectFit: 'cover',
          flexShrink: 0,
          bgcolor: 'action.hover',
          cursor: 'pointer',
          filter: blurred ? 'blur(8px)' : 'none',
        }}
      />
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Typography
          component={RouterLink}
          to={`/audiobooks/${book.slug}`}
          variant="body2"
          noWrap
          sx={{ display: 'block', fontWeight: 600, color: 'text.primary', textDecoration: 'none' }}
        >
          {book.title}
        </Typography>
        <Typography variant="caption" color="text.secondary" noWrap component="div">
          {chapter.title}
          {' · '}
          {failed ? t('audioPlayer.playbackError') : `${formatClock(position)} / ${formatClock(duration)}`}
        </Typography>
      </Box>
      <Tooltip title={t('audioPlayer.rewind')}>
        <IconButton aria-label={t('audioPlayer.rewind')} onClick={() => player.skip(-15)} size="small">
          <ReplayIcon />
        </IconButton>
      </Tooltip>
      <Tooltip title={playing ? t('audioPlayer.pause') : t('audioPlayer.play')}>
        {/* A disabled button emits no pointer events, so the tooltip needs a span around it. */}
        <span>
          <IconButton
            aria-label={playing ? t('audioPlayer.pause') : t('audioPlayer.play')}
            onClick={player.toggle}
            disabled={loading}
            color="primary"
          >
            {playing ? <PauseIcon /> : <PlayArrowIcon />}
          </IconButton>
        </span>
      </Tooltip>
      <Tooltip title={t('audioPlayer.forward')}>
        <IconButton aria-label={t('audioPlayer.forward')} onClick={() => player.skip(30)} size="small">
          <Forward30Icon />
        </IconButton>
      </Tooltip>
      <Tooltip title={t('audioPlayer.expand')}>
        <IconButton aria-label={t('audioPlayer.expand')} onClick={() => player.expand(true)} size="small">
          <KeyboardArrowUpIcon />
        </IconButton>
      </Tooltip>
      <Tooltip title={t('audioPlayer.close')}>
        <IconButton aria-label={t('audioPlayer.close')} onClick={player.close} size="small">
          <CloseIcon />
        </IconButton>
      </Tooltip>
      <Box
        role="presentation"
        sx={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: 0,
          height: 3,
          bgcolor: 'action.hover',
        }}
      >
        <Box
          sx={{
            height: '100%',
            width: `${percent}%`,
            bgcolor: 'primary.main',
            transition: reducedMotion ? 'none' : 'width 0.5s linear',
          }}
        />
      </Box>
    </Paper>
  );
};

export default MiniPlayer;
