import React, { useEffect, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import {
  Box,
  Button,
  Dialog,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Menu,
  MenuItem,
  Slider,
  Stack,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import Forward30Icon from '@mui/icons-material/Forward30';
import ReplayIcon from '@mui/icons-material/Replay';
import SkipNextIcon from '@mui/icons-material/SkipNext';
import SkipPreviousIcon from '@mui/icons-material/SkipPrevious';
import BedtimeOutlinedIcon from '@mui/icons-material/BedtimeOutlined';
import BedtimeIcon from '@mui/icons-material/Bedtime';
import CheckIcon from '@mui/icons-material/Check';
import CloseIcon from '@mui/icons-material/Close';
import { useTranslation } from 'react-i18next';
import { useAudioPlayer, useAudioPlayerTime, type SleepOption } from '@context/AudioPlayerContext';
import { useAdultContent } from '@context/AdultContentContext';
import { AdultBadge } from '@components/common/AdultBadge';
import { audiobookRevealKey, audioChapterLabel } from '@utils/audiobook';
import { formatClock } from '@utils/duration';

const SPEEDS = [0.75, 1, 1.25, 1.5, 1.75, 2, 2.25, 2.5];
const SLEEP_MINUTES = [15, 30, 45, 60];

// Full player: a bottom drawer on small screens, a dialog elsewhere. Controls, speed, sleep timer and chapter list.
const FullPlayer: React.FC = () => {
  const { t } = useTranslation();
  const theme = useTheme();
  const small = useMediaQuery(theme.breakpoints.down('sm'));
  const player = useAudioPlayer();
  const { position, duration } = useAudioPlayerTime();
  const { isBlurred, revealHandler } = useAdultContent();
  const { book, queue, index, chapter, status, speed, sleep, expanded } = player;
  const [dragging, setDragging] = useState<number | null>(null);
  const [speedAnchor, setSpeedAnchor] = useState<HTMLElement | null>(null);
  const [sleepAnchor, setSleepAnchor] = useState<HTMLElement | null>(null);
  const [, setTick] = useState(0);

  // The remaining time of a timed sleep is shown only in the open player: refresh it every second while it is open.
  const sleepCountdown = sleep?.type === 'time' && expanded;
  useEffect(() => {
    if (!sleepCountdown) return;
    const id = window.setInterval(() => setTick((value) => value + 1), 1000);
    return () => window.clearInterval(id);
  }, [sleepCountdown]);

  if (!book || !chapter) return null;

  const playing = status === 'playing';
  const loading = status === 'loading';
  const failed = status === 'error';
  const shownPosition = dragging ?? position;
  const revealKey = audiobookRevealKey(book.slug, book.language);
  const blurred = isBlurred(book.is_adult, revealKey);
  const sleepLabel = sleep === null
    ? t('audioPlayer.sleepOff')
    : sleep.type === 'chapterEnd'
      ? t('audioPlayer.sleepChapterEnd')
      : t('audioPlayer.sleepRemaining', {
        time: formatClock((sleep.endsAt - Date.now()) / 1000),
      });

  const pickSleep = (option: SleepOption | null) => {
    player.setSleep(option);
    setSleepAnchor(null);
  };

  const body = (
    <Stack spacing={2} sx={{ p: 3 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'flex-start' }}>
        <Box sx={{ position: 'relative', width: 96, height: 96, borderRadius: 1, flexShrink: 0, bgcolor: 'action.hover' }}>
          <Box
            component="img"
            src={(book.cover_jpg_url ?? book.cover_url) ?? undefined}
            alt=""
            onClick={blurred ? revealHandler(revealKey) : undefined}
            sx={{
              width: 96,
              height: 96,
              borderRadius: 1,
              objectFit: 'cover',
              display: 'block',
              filter: blurred ? 'blur(16px)' : 'none',
              cursor: blurred ? 'pointer' : undefined,
            }}
          />
          <AdultBadge isAdult={book.is_adult} novelId={revealKey} />
        </Box>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, lineHeight: 1.3 }}>
            {book.title}
          </Typography>
          <Typography variant="caption" color="text.secondary" component="div">
            {t('audioPlayer.generatedCaption')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {audioChapterLabel(t, chapter.number, chapter.title)}
          </Typography>
        </Box>
        <IconButton aria-label={t('audioPlayer.close')} onClick={() => player.expand(false)}>
          <CloseIcon />
        </IconButton>
      </Stack>

      <Box>
        <Slider
          value={shownPosition}
          min={0}
          max={duration > 0 ? duration : 1}
          disabled={loading || duration <= 0}
          aria-label={t('audioPlayer.seek')}
          getAriaValueText={() => t('audioPlayer.seekValue', {
            current: formatClock(shownPosition),
            total: formatClock(duration),
          })}
          onChange={(_, value) => setDragging(value as number)}
          onChangeCommitted={(_, value) => {
            player.seekTo(value as number);
            setDragging(null);
          }}
        />
        <Stack direction="row" sx={{ justifyContent: 'space-between' }}>
          <Typography variant="caption" color="text.secondary">{formatClock(shownPosition)}</Typography>
          <Typography variant="caption" color="text.secondary">{formatClock(duration)}</Typography>
        </Stack>
      </Box>

      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'center' }}>
        <IconButton aria-label={t('audioPlayer.previous')} onClick={player.prev}>
          <SkipPreviousIcon />
        </IconButton>
        <IconButton aria-label={t('audioPlayer.rewind')} onClick={() => player.skip(-15)}>
          <ReplayIcon />
        </IconButton>
        <IconButton
          aria-label={playing ? t('audioPlayer.pause') : t('audioPlayer.play')}
          onClick={player.toggle}
          disabled={loading}
          color="primary"
          sx={{ bgcolor: 'primary.main', color: 'primary.contrastText', '&:hover': { bgcolor: 'primary.dark' } }}
        >
          {playing ? <PauseIcon fontSize="large" /> : <PlayArrowIcon fontSize="large" />}
        </IconButton>
        <IconButton aria-label={t('audioPlayer.forward')} onClick={() => player.skip(30)}>
          <Forward30Icon />
        </IconButton>
        <IconButton aria-label={t('audioPlayer.next')} onClick={player.next}>
          <SkipNextIcon />
        </IconButton>
      </Stack>

      {failed && (
        <Typography variant="body2" color="error" sx={{ textAlign: 'center' }}>
          {t('audioPlayer.playbackError')}
        </Typography>
      )}

      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
        <Button variant="outlined" size="small" onClick={(event) => setSpeedAnchor(event.currentTarget)}>
          {t('audioPlayer.speedValue', { speed })}
        </Button>
        <Button
          variant="outlined"
          size="small"
          startIcon={sleep ? <BedtimeIcon /> : <BedtimeOutlinedIcon />}
          onClick={(event) => setSleepAnchor(event.currentTarget)}
        >
          {sleepLabel}
        </Button>
        <Button component={RouterLink} to={`/audiobooks/${book.slug}`} size="small" onClick={() => player.expand(false)}>
          {t('audioPlayer.openAudiobook')}
        </Button>
        <Button
          component={RouterLink}
          to={`/novels/${book.novel_slug}/${book.source_slug}/chapter/${chapter.number}`}
          size="small"
          onClick={() => player.expand(false)}
        >
          {t('audioPlayer.readChapter')}
        </Button>
      </Stack>

      <Menu anchorEl={speedAnchor} open={speedAnchor !== null} onClose={() => setSpeedAnchor(null)}>
        {SPEEDS.map((value) => (
          <MenuItem
            key={value}
            selected={value === speed}
            onClick={() => {
              player.setSpeed(value);
              setSpeedAnchor(null);
            }}
          >
            {t('audioPlayer.speedValue', { speed: value })}
          </MenuItem>
        ))}
      </Menu>

      <Menu anchorEl={sleepAnchor} open={sleepAnchor !== null} onClose={() => setSleepAnchor(null)}>
        <MenuItem selected={sleep === null} onClick={() => pickSleep(null)}>{t('audioPlayer.sleepOff')}</MenuItem>
        <MenuItem selected={sleep?.type === 'chapterEnd'} onClick={() => pickSleep({ type: 'chapterEnd' })}>
          {t('audioPlayer.sleepChapterEnd')}
        </MenuItem>
        {SLEEP_MINUTES.map((minutes) => (
          <MenuItem key={minutes} onClick={() => pickSleep({ type: 'time', minutes })}>
            {t('audioPlayer.sleepMinutes', { count: minutes })}
          </MenuItem>
        ))}
      </Menu>

      <Box>
        <Typography variant="subtitle2" gutterBottom>{t('audioPlayer.chapters')}</Typography>
        <List dense disablePadding sx={{ maxHeight: 240, overflowY: 'auto' }}>
          {queue.map((item, i) => (
            <ListItemButton
              key={item.chapter_id}
              selected={i === index}
              onClick={() => player.playChapter(i)}
            >
              {i < index && <CheckIcon fontSize="small" color="success" aria-label={t('audiobooks.chapterListened')} />}
              <ListItemText
                primary={audioChapterLabel(t, item.number, item.title)}
                secondary={formatClock(item.duration_s)}
              />
            </ListItemButton>
          ))}
        </List>
      </Box>
    </Stack>
  );

  const onClose = () => player.expand(false);

  if (small) {
    return (
      <Drawer
        anchor="bottom"
        open={expanded}
        onClose={onClose}
        slotProps={{ paper: { sx: { maxHeight: '90vh', borderTopLeftRadius: 16, borderTopRightRadius: 16 } } }}
      >
        {body}
      </Drawer>
    );
  }

  return (
    <Dialog open={expanded} onClose={onClose} fullWidth maxWidth="sm" aria-label={t('audioPlayer.nowPlaying')}>
      {body}
    </Dialog>
  );
};

export default FullPlayer;
