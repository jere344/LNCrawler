import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Box, Button, Typography, alpha, useTheme } from '@mui/material';
import HeadphonesIcon from '@mui/icons-material/Headphones';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { useAudioPlayer } from '@context/AudioPlayerContext';
import { useAdultContent } from '@context/AdultContentContext';
import { AdultBadge } from '@components/common/AdultBadge';
import { formatHours } from '@utils/duration';
import { audiobookPath, audiobookRevealKey } from '@utils/audiobook';

interface SourceAudiobookBannerProps {
  audiobook: { slug: string; language: string; duration_s: number; is_adult?: boolean };
  // The source is adult (or its novel is): the banner is blurred like the adult covers.
  isAdult?: boolean;
}

// Slim strip on a source page that has an audiobook edition: starts it in the player or opens its page.
const SourceAudiobookBanner = ({ audiobook, isAdult }: SourceAudiobookBannerProps) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const { playAudiobook } = useAudioPlayer();
  const { isBlurred, revealHandler } = useAdultContent();
  const revealKey = audiobookRevealKey(audiobook.slug, audiobook.language);
  const blurred = isBlurred(isAdult, revealKey);

  return (
    <Box sx={{
      position: 'relative',
      display: 'flex',
      alignItems: 'center',
      flexWrap: 'wrap',
      gap: 1,
      px: 2,
      py: 1,
      mt: 1.5,
      borderRadius: 2,
      bgcolor: alpha(theme.palette.primary.main, 0.08),
      border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
    }}>
      <HeadphonesIcon color="primary" />
      <Typography
        variant="body2"
        onClick={blurred ? revealHandler(revealKey) : undefined}
        sx={{ flex: { xs: '1 1 calc(100% - 40px)', sm: 1 }, minWidth: 0, filter: blurred ? 'blur(6px)' : 'none', cursor: blurred ? 'pointer' : undefined }}
      >
        {t('audiobooks.sourceBanner', { hours: formatHours(audiobook.duration_s, t) })}
      </Typography>
      <AdultBadge isAdult={isAdult} novelId={revealKey} />
      <Button size="small" variant="contained" startIcon={<PlayArrowIcon />} onClick={() => void playAudiobook(audiobook.slug, audiobook.language)}>
        {t('audiobooks.listen')}
      </Button>
      <Button size="small" component={Link} to={audiobookPath(audiobook.slug, audiobook.language)}>
        {t('audiobooks.open')}
      </Button>
    </Box>
  );
};

export default SourceAudiobookBanner;
