import { Container, Typography, Box, CircularProgress } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { UnavailableChapterInfo } from '@models/novels_types';
import UnavailableChapter from '../UnavailableChapter';

interface ChapterStatusViewProps {
  loading: boolean;
  error: string | null;
  unavailableChapter: UnavailableChapterInfo | null;
  novelSlug?: string;
  sourceSlug?: string;
}

// Shown in place of the text while the chapter loads, is unavailable, or failed to load
const ChapterStatusView = ({
  loading,
  error,
  unavailableChapter,
  novelSlug,
  sourceSlug,
}: ChapterStatusViewProps) => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  if (loading) {
    return (
      <Container>
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 8 }}>
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  if (unavailableChapter) {
    return (
      <UnavailableChapter
        info={unavailableChapter}
        onNextAvailable={
          unavailableChapter.next_chapter != null
            ? () => navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${unavailableChapter.next_chapter}`)
            : undefined
        }
        onPrevious={
          unavailableChapter.prev_chapter != null
            ? () => navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${unavailableChapter.prev_chapter}`)
            : undefined
        }
        onChapterList={() => navigate(`/novels/${novelSlug}/${sourceSlug}/chapterlist`)}
      />
    );
  }

  return (
    <Container>
      <Box sx={{ p: 3, textAlign: 'center', mt: 3 }}>
        <Typography color="error">{error || t('reader.notFound')}</Typography>
      </Box>
    </Container>
  );
};

export default ChapterStatusView;
