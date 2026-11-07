import { Box, Skeleton, alpha, useTheme } from '@mui/material';
import { useTranslation } from 'react-i18next';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import SkipNextIcon from '@mui/icons-material/SkipNext';
import BookmarkIcon from '@mui/icons-material/Bookmark';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import ActionButton from '../../common/ActionButton';
import { NovelFromSource as ISourceDetail, type Chapter } from '@models/novels_types';

// `source` is null while the page only has a library preview: the actions wait for the full source.
const SourceReadActions = ({
  source,
  novelSlug,
  sourceSlug,
  isDmca,
}: {
  source: ISourceDetail | null;
  novelSlug: string | undefined;
  sourceSlug: string | undefined;
  isDmca: boolean;
}) => {
  const { t } = useTranslation();
  const theme = useTheme();
  if (!source) {
    return <Skeleton variant="rounded" height={56} sx={{ mb: 1.5, bgcolor: alpha(theme.palette.common.white, 0.2) }} />;
  }
  const history = source.reading_history;
  // The row may point at another source of the novel: Continue then opens that one
  const rowSourceSlug = history?.source_slug || sourceSlug;
  const onOtherSource = rowSourceSlug !== sourceSlug;
  // Continue resumes at the saved position; when up to date, the chapter being read is offered to reread
  const resume = history?.resume ?? null;
  const reread = history && !resume ? history.current_chapter : null;
  const chapterLabel = (chapter: Chapter): string => (
    onOtherSource && history
      ? t('sourceDetail.chapterOnSource', { chapter: chapter.display_title, source: history.source_name })
      : chapter.display_title
  );
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: {
          xs: '1fr',
          lg: (resume || reread) && !isDmca ? 'repeat(3, 1fr)' : 'repeat(2, 1fr)',
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

      {resume && !isDmca && (
        <ActionButton
          title={t('sourceDetail.continueReading')}
          subtitle={chapterLabel(resume.chapter)}
          startIcon={<BookmarkIcon />}
          color="warning"
          to={`/novels/${novelSlug}/${rowSourceSlug}/chapter/${resume.chapter.chapter_id}`}
          state={{ resumeProgress: resume.progress }}
          tooltip={t('sourceDetail.continueFrom', { chapter: chapterLabel(resume.chapter) })}
        />
      )}

      {reread && !isDmca && (
        <ActionButton
          title={t('cards.reread')}
          subtitle={t('sourceDetail.upToDate', { chapter: chapterLabel(reread) })}
          startIcon={<MenuBookIcon />}
          color="secondary"
          to={`/novels/${novelSlug}/${rowSourceSlug}/chapter/${reread.chapter_id}`}
        />
      )}

      <ActionButton
        title={t('sourceDetail.latestChapter')}
        subtitle={source?.latest_available_chapter?.display_title}
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
