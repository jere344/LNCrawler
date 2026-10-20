import { Box } from '@mui/material';
import { useTranslation } from 'react-i18next';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import SkipNextIcon from '@mui/icons-material/SkipNext';
import BookmarkIcon from '@mui/icons-material/Bookmark';
import ActionButton from '../../common/ActionButton';
import { getChapterLabel } from '@utils/Misc.tsx';
import { NovelFromSource as ISourceDetail } from '@models/novels_types';

const SourceReadActions = ({
  source,
  novelSlug,
  sourceSlug,
  isDmca,
}: {
  source: ISourceDetail;
  novelSlug: string | undefined;
  sourceSlug: string | undefined;
  isDmca: boolean;
}) => {
  const { t } = useTranslation();
  const continue_chapter = source.reading_history?.next_chapter || source.reading_history?.last_read_chapter;
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: {
          xs: '1fr',
          lg: continue_chapter && !isDmca ? 'repeat(3, 1fr)' : 'repeat(2, 1fr)',
        },
        gap: 1,
        mb: 1.5,
      }}
    >
      <ActionButton
        title={t('sourceDetail.startReading')}
        subtitle={t('sourceDetail.fromBeginning')}
        startIcon={<PlayArrowIcon />}
        color="success"
        to={`/novels/${novelSlug}/${sourceSlug}/chapter/${source.first_available_chapter?.chapter_id}`}
        disabled={isDmca || !source.first_available_chapter}
        tooltip={t('sourceDetail.startFromFirst')}
      />

      {continue_chapter && !isDmca && (
        <ActionButton
          title={t('sourceDetail.continueReading')}
          subtitle={getChapterLabel(t, continue_chapter.title, continue_chapter.chapter_id)}
          startIcon={<BookmarkIcon />}
          color="warning"
          to={`/novels/${novelSlug}/${sourceSlug}/chapter/${continue_chapter.chapter_id}`}
          tooltip={t('sourceDetail.continueFrom', { chapter: getChapterLabel(t, continue_chapter.title, continue_chapter.chapter_id) })}
        />
      )}

      <ActionButton
        title={t('sourceDetail.latestChapter')}
        subtitle={getChapterLabel(t, source?.latest_available_chapter?.title, source?.latest_available_chapter?.chapter_id)}
        startIcon={<SkipNextIcon />}
        color="primary"
        to={`/novels/${novelSlug}/${sourceSlug}/chapter/${source?.latest_available_chapter?.chapter_id || 0}`}
        disabled={isDmca || !source?.latest_available_chapter}
        tooltip={t('sourceDetail.jumpToLatest')}
      />
    </Box>
  );
};

export default SourceReadActions;
