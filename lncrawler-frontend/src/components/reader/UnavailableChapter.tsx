import { Container, Paper, Typography, Button, Stack } from '@mui/material';
import BlockIcon from '@mui/icons-material/Block';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import ListAltIcon from '@mui/icons-material/ListAlt';
import { useTranslation } from 'react-i18next';
import { getChapterLabel } from '@utils/Misc';
import { UnavailableChapterInfo } from '@models/novels_types';

interface UnavailableChapterProps {
  info: UnavailableChapterInfo;
  onPrevious?: () => void;
  onNextAvailable?: () => void;
  onChapterList: () => void;
}

/**
 * Shown when a chapter exists but has no content, instead of silently jumping
 * over it. Offers an explicit "go to next available" so the skip is deliberate.
 */
const UnavailableChapter: React.FC<UnavailableChapterProps> = ({
  info,
  onPrevious,
  onNextAvailable,
  onChapterList,
}) => {
  const { t } = useTranslation();

  return (
    <Container maxWidth="sm">
      <Paper elevation={3} sx={{ p: 4, mt: 6, textAlign: 'center' }}>
        <BlockIcon color="disabled" sx={{ fontSize: 56, mb: 1 }} />
        <Typography variant="h5" gutterBottom>
          {t('reader.unavailableTitle', { chapter: info.chapter_id })}
        </Typography>
        <Typography variant="subtitle1" color="text.secondary" gutterBottom>
          {getChapterLabel(t, info.title, info.chapter_id)}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          {t('reader.unavailableMessage')}
        </Typography>
        <Stack spacing={1.5} alignItems="stretch" sx={{ maxWidth: 320, mx: 'auto' }}>
          {onNextAvailable && info.next_chapter != null && (
            <Button
              variant="contained"
              endIcon={<ArrowForwardIcon />}
              onClick={onNextAvailable}
            >
              {t('reader.goToNextAvailable', { chapter: info.next_chapter })}
            </Button>
          )}
          {onPrevious && info.prev_chapter != null && (
            <Button
              variant="outlined"
              startIcon={<ArrowBackIcon />}
              onClick={onPrevious}
            >
              {t('reader.goToPrevious')}
            </Button>
          )}
          <Button startIcon={<ListAltIcon />} onClick={onChapterList}>
            {t('reader.chapters')}
          </Button>
        </Stack>
      </Paper>
    </Container>
  );
};

export default UnavailableChapter;
