import { Box, IconButton, LinearProgress, Typography, alpha, useTheme } from '@mui/material';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import HeadphonesIcon from '@mui/icons-material/Headphones';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { useAudioPlayer } from '@context/AudioPlayerContext';
import { useAdultContent } from '@context/AdultContentContext';
import { AdultBadge } from '@components/common/AdultBadge';
import type { AudiobookCard as AudiobookCardData } from '@models/audiobook_types';
import { formatHours } from '@utils/duration';
import { audiobookPath, audiobookRevealKey, progressRatio } from '@utils/audiobook';
import LanguageFlag from './LanguageFlag';

interface AudiobookCardProps {
  book: AudiobookCardData;
}

// Square cover card. The title link is stretched over the whole card; the play button sits outside
// the link (and above the stretched area), so no interactive elements are nested.
const AudiobookCard = ({ book }: AudiobookCardProps) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const { playAudiobook } = useAudioPlayer();
  const { isBlurred } = useAdultContent();
  const revealKey = audiobookRevealKey(book.slug, book.language);
  const blurred = isBlurred(book.is_adult, revealKey);
  const cover = book.cover_url || book.cover_jpg_url;

  return (
    <Box sx={{ position: 'relative', minWidth: 0 }}>
      <Box
        sx={{
          position: 'relative',
          aspectRatio: '1 / 1',
          borderRadius: 2,
          overflow: 'hidden',
          bgcolor: alpha(theme.palette.primary.main, 0.08),
          boxShadow: theme.shadows[2],
        }}
      >
        {cover ? (
          <Box
            component="img"
            src={cover}
            alt=""
            loading="lazy"
            sx={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', filter: blurred ? 'blur(16px)' : 'none' }}
          />
        ) : (
          <Box sx={{ width: '100%', height: '100%', display: 'grid', placeItems: 'center' }}>
            <HeadphonesIcon sx={{ fontSize: 48, color: 'text.disabled' }} />
          </Box>
        )}
        <AdultBadge isAdult={book.is_adult} novelId={revealKey} />
        <LanguageFlag language={book.language} />
        <IconButton
          aria-label={t('audiobooks.playBook', { title: book.title })}
          onClick={() => void playAudiobook(book.slug, book.language)}
          sx={{
            position: 'absolute',
            right: 8,
            bottom: 8,
            zIndex: 1,
            bgcolor: 'primary.main',
            color: 'primary.contrastText',
            boxShadow: theme.shadows[4],
            '&:hover': { bgcolor: 'primary.dark' },
          }}
        >
          <PlayArrowIcon />
        </IconButton>
      </Box>

      {book.progress && (
        <LinearProgress
          variant="determinate"
          value={progressRatio(book) * 100}
          aria-label={t('audiobooks.progressLabel')}
          sx={{ mt: 0.75, height: 3, borderRadius: 2 }}
        />
      )}

      <Typography
        component={Link}
        to={audiobookPath(book.slug, book.language)}
        variant="subtitle2"
        sx={{
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
          mt: 1,
          color: 'text.primary',
          textDecoration: 'none',
          fontWeight: 600,
          '&::after': { content: '""', position: 'absolute', inset: 0 },
          '&:focus-visible': { outline: 'none' },
          '&:focus-visible::after': { outline: `2px solid ${theme.palette.primary.main}`, outlineOffset: 2 },
        }}
      >
        {book.title}
      </Typography>

      <Typography variant="caption" color="text.secondary" noWrap component="p" sx={{ mt: 0.25, mb: 0 }}>
        {book.authors.join(', ') || t('common.unknown')}
      </Typography>
      <Typography variant="caption" color="text.secondary" component="p" sx={{ mb: 0 }}>
        {t('audiobooks.cardMeta', {
          hours: formatHours(book.duration_s, t),
          count: book.parts,
        })}
      </Typography>
    </Box>
  );
};

export default AudiobookCard;
