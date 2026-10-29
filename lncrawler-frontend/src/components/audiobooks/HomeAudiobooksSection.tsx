import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Box, Button, Divider, Typography, alpha, useTheme } from '@mui/material';
import HeadphonesIcon from '@mui/icons-material/Headphones';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import type { AudiobookCard as AudiobookCardData, HomeAudiobooks } from '@models/audiobook_types';
import { useAudioPlayer } from '@context/AudioPlayerContext';
import { useAuth } from '@context/AuthContext';
import { useAdultContent } from '@context/AdultContentContext';
import { AdultBadge } from '@components/common/AdultBadge';
import { formatHours } from '@utils/duration';
import AudiobookCard from './AudiobookCard';
import LanguageFlag from './LanguageFlag';
import { audiobookPath, audiobookRevealKey } from '@utils/audiobook';

// Horizontal row of covers, scrolled with the mouse wheel or touch.
const rowSx = {
  display: 'flex',
  gap: 2,
  overflowX: 'auto',
  scrollSnapType: 'x mandatory',
  pb: 1,
  '& > *': { flex: '0 0 140px', scrollSnapAlign: 'start' },
} as const;

const Row = ({ title, books }: { title: string; books: AudiobookCardData[] }) => {
  if (books.length === 0) return null;
  return (
    <Box sx={{ mb: 4 }}>
      <Typography variant="h6" component="h3" sx={{ fontWeight: 'bold', mb: 1.5 }}>{title}</Typography>
      <Box sx={rowSx}>
        {books.map(book => <AudiobookCard key={`${book.slug}-${book.language}`} book={book} />)}
      </Box>
    </Box>
  );
};

// Wide card for the featured audiobook: cover on the left, the start button and the page link on the right.
const FeaturedCard = ({ book }: { book: AudiobookCardData }) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const { playAudiobook } = useAudioPlayer();
  const { isBlurred } = useAdultContent();
  const revealKey = audiobookRevealKey(book.slug, book.language);
  const blurred = isBlurred(book.is_adult, revealKey);
  const cover = book.cover_url || book.cover_jpg_url;

  return (
    <Box sx={{
      display: 'flex',
      gap: 2,
      p: 2,
      mb: 4,
      borderRadius: 2,
      bgcolor: alpha(theme.palette.primary.main, 0.06),
      boxShadow: theme.shadows[1],
    }}>
      <Box sx={{ position: 'relative', width: { xs: 120, sm: 180 }, flexShrink: 0, aspectRatio: '1 / 1', borderRadius: 2, overflow: 'hidden', bgcolor: 'action.hover' }}>
        {cover ? (
          <Box component="img" src={cover} alt="" loading="lazy" sx={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', filter: blurred ? 'blur(16px)' : 'none' }} />
        ) : (
          <Box sx={{ width: '100%', height: '100%', display: 'grid', placeItems: 'center' }}>
            <HeadphonesIcon sx={{ fontSize: 48, color: 'text.disabled' }} />
          </Box>
        )}
        <AdultBadge isAdult={book.is_adult} novelId={revealKey} />
        <LanguageFlag language={book.language} />
      </Box>
      <Box sx={{ minWidth: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
        <Typography variant="h6" component="h3" sx={{ fontWeight: 700 }}>{book.title}</Typography>
        {book.authors.length > 0 && (
          <Typography variant="body2" color="text.secondary" noWrap>{book.authors.join(', ')}</Typography>
        )}
        <Typography variant="body2" color="text.secondary">
          {t('audiobooks.cardMeta', {
            hours: formatHours(book.duration_s, t),
            count: book.parts,
          })}
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 1.5 }}>
          <Button variant="contained" size="small" startIcon={<PlayArrowIcon />} onClick={() => void playAudiobook(book.slug, book.language)}>
            {t('audiobooks.listenNow')}
          </Button>
          <Button variant="outlined" size="small" component={Link} to={audiobookPath(book.slug, book.language)}>
            {t('audiobooks.openPage')}
          </Button>
        </Box>
      </Box>
    </Box>
  );
};

interface HomeAudiobooksSectionProps {
  audiobooks: HomeAudiobooks | undefined;
}

// Home block for audiobooks: the featured book, popular covers and (for signed-in viewers) the books
// they are part way through.
const HomeAudiobooksSection = ({ audiobooks }: HomeAudiobooksSectionProps) => {
  const { t } = useTranslation();
  const { isAuthenticated } = useAuth();

  const featured = audiobooks?.featured ?? null;
  const popular = audiobooks?.popular ?? [];
  const continueListening = isAuthenticated ? (audiobooks?.continue_listening ?? []) : [];
  const hasAudiobooks = Boolean(featured || popular.length > 0);
  if (!hasAudiobooks && continueListening.length === 0) return null;

  return (
    <Box sx={{ mb: 6 }}>
      {hasAudiobooks && (
        <>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h5" component="h2" sx={{ fontWeight: 'bold' }}>{t('audiobooks.homeTitle')}</Typography>
            <Button component={Link} to="/audiobooks">{t('audiobooks.viewAll')}</Button>
          </Box>
          <Divider sx={{ mb: 3 }} />
          {featured && <FeaturedCard book={featured} />}
          <Row title={t('audiobooks.popularTitle')} books={popular} />
        </>
      )}

      {continueListening.length > 0 && (
        <>
          {!hasAudiobooks && <Divider sx={{ mb: 3 }} />}
          <Row title={t('audiobooks.continueListening')} books={continueListening} />
        </>
      )}
    </Box>
  );
};

export default HomeAudiobooksSection;
