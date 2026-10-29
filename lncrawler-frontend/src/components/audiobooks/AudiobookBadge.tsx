import { useTranslation } from 'react-i18next';
import { Box } from '@mui/material';
import HeadphonesIcon from '@mui/icons-material/Headphones';

// Small headphones mark on a cover that has an audiobook. Sits in the bottom-right corner, which is
// free on the cover cards (the language flags are on top, the DMCA and adult badges on the left).
export const AudiobookBadge = () => {
  const { t } = useTranslation();
  return (
    <Box
      role="img"
      aria-label={t('audiobooks.badge')}
      title={t('audiobooks.badge')}
      sx={{
        position: 'absolute',
        right: 8,
        bottom: 8,
        zIndex: 2,
        display: 'grid',
        placeItems: 'center',
        width: 26,
        height: 26,
        borderRadius: '50%',
        bgcolor: 'primary.main',
        color: 'primary.contrastText',
        boxShadow: 2,
        pointerEvents: 'none',
      }}
    >
      <HeadphonesIcon sx={{ fontSize: 16 }} />
    </Box>
  );
};

export default AudiobookBadge;
