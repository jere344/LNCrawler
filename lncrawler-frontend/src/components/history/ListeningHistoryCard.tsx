import React from 'react';
import { Link } from 'react-router-dom';
import {
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  IconButton,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import HeadphonesIcon from '@mui/icons-material/Headphones';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { useTranslation } from 'react-i18next';
import { useAudioPlayer } from '@context/AudioPlayerContext';
import { useAdultContent } from '@context/AdultContentContext';
import { AdultBadge } from '@components/common/AdultBadge';
import type { ListeningHistoryEntry } from '@models/audiobook_types';
import { audiobookPath, audiobookRevealKey, progressRatio } from '@utils/audiobook';
import { formatClock } from '@utils/duration';
import { formatDate } from '@utils/Misc';

interface ListeningHistoryCardProps {
  entry: ListeningHistoryEntry;
  onDelete: () => void;
}

// A listening entry of the history: cover, title, last chapter and position, progress, and resume or page links.
const ListeningHistoryCard: React.FC<ListeningHistoryCardProps> = ({ entry, onDelete }) => {
  const { t, i18n } = useTranslation();
  const { playAudiobook } = useAudioPlayer();
  const { isBlurred, revealHandler } = useAdultContent();
  const { audiobook } = entry;
  const revealKey = audiobookRevealKey(audiobook.slug, audiobook.language);
  const blurred = isBlurred(audiobook.is_adult, revealKey);
  const cover = audiobook.cover_url || audiobook.cover_jpg_url;
  const progress = audiobook.progress;
  const pagePath = audiobookPath(audiobook.slug, audiobook.language);

  return (
    <Card
      elevation={2}
      sx={{
        display: 'flex',
        position: 'relative',
        overflow: 'visible',
        height: '100%',
        '&:hover': {
          boxShadow: 6
        }
      }}
    >
      <Tooltip title={t('history.removeListen')}>
        <IconButton
          size="medium"
          aria-label={t('history.removeListen')}
          onClick={onDelete}
          sx={{ position: 'absolute', top: 8, right: 8, zIndex: 2 }}
        >
          <CloseIcon fontSize="medium" />
        </IconButton>
      </Tooltip>

      <Box sx={{ position: 'relative', width: 120, minWidth: 120, bgcolor: 'action.hover', borderTopLeftRadius: 4, borderBottomLeftRadius: 4, overflow: 'hidden' }}>
        {cover ? (
          <Box
            component="img"
            src={cover}
            alt=""
            loading="lazy"
            onClick={blurred ? revealHandler(revealKey) : undefined}
            sx={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', filter: blurred ? 'blur(16px)' : 'none', cursor: blurred ? 'pointer' : undefined }}
          />
        ) : (
          <Box sx={{ width: '100%', height: '100%', display: 'grid', placeItems: 'center' }}>
            <HeadphonesIcon sx={{ fontSize: 40, color: 'text.disabled' }} />
          </Box>
        )}
        <AdultBadge isAdult={audiobook.is_adult} novelId={revealKey} />
      </Box>

      <Box sx={{ display: 'flex', flexDirection: 'column', flexGrow: 1, minWidth: 0, width: '100%' }}>
        <CardContent sx={{ pb: 1, flexGrow: 1 }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', pr: 5 }}>
            <Box role="img" aria-label={t('history.kindListen')} sx={{ display: 'flex', color: 'primary.main', flexShrink: 0 }}>
              <HeadphonesIcon fontSize="small" />
            </Box>
            <Typography
              variant="h6"
              component={Link}
              to={pagePath}
              sx={{
                fontWeight: 'bold',
                minWidth: 0,
                color: 'text.primary',
                textDecoration: 'none',
                '&:hover': { color: 'primary.main' },
              }}
            >
              {audiobook.title}
            </Typography>
          </Stack>

          {progress?.chapter_number != null && (
            <Typography variant="body2" sx={{ mt: 1 }}>
              {t('history.listenChapter', { number: progress.chapter_number, time: formatClock(progress.position_s) })}
            </Typography>
          )}

          <LinearProgress
            variant="determinate"
            value={progressRatio(audiobook) * 100}
            aria-label={t('audiobooks.progressLabel')}
            sx={{ mt: 1, height: 4, borderRadius: 2 }}
          />

          <Typography
            variant="caption"
            sx={{
              display: 'block',
              color: 'text.secondary',
              mt: 1
            }}>
            {formatDate(entry.at, i18n.language)}
          </Typography>
        </CardContent>

        <CardActions sx={{ pt: 0 }}>
          <Button
            size="small"
            color="primary"
            variant="contained"
            startIcon={<PlayArrowIcon />}
            sx={{ mr: 1 }}
            onClick={() => void playAudiobook(audiobook.slug, audiobook.language)}
          >
            {t('history.resume')}
          </Button>
          <Button
            size="small"
            color="secondary"
            variant="outlined"
            component={Link}
            to={pagePath}
          >
            {t('history.audiobookPage')}
          </Button>
        </CardActions>
      </Box>
    </Card>
  );
};

export default ListeningHistoryCard;
