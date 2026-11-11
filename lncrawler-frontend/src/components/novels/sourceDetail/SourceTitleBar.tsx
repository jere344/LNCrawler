import type { Dispatch, SetStateAction } from 'react';
import { Box, Chip, IconButton, Tooltip, Typography, alpha, useTheme } from '@mui/material';
import { useTranslation } from 'react-i18next';
import BookmarkBorderIcon from '@mui/icons-material/BookmarkBorder';
import BookmarkIcon from '@mui/icons-material/Bookmark';
import PlaylistAddIcon from '@mui/icons-material/PlaylistAdd';
import MarkAsReadButton from '../../common/MarkAsReadButton';
import { SourceView, NovelDetail as INovelDetail } from '@models/novels_types';
import { isFullSource } from './sourceView';

const SourceTitleBar = ({
  source,
  novel,
  novelSlug,
  isAuthenticated,
  isBookmarked,
  bookmarking,
  onToggleBookmark,
  onAddToList,
  setSource,
}: {
  source: SourceView;
  novel: INovelDetail | null;
  novelSlug: string | undefined;
  isAuthenticated: boolean;
  isBookmarked: boolean;
  bookmarking: boolean;
  onToggleBookmark: () => void;
  onAddToList: () => void;
  setSource: Dispatch<SetStateAction<SourceView | null>>;
}) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const full = isFullSource(source) ? source : null;
  const adultTags = full?.adult_tags ?? [];
  // The row may point at another source of the novel: mark-all then goes to this page's source, from its own latest chapter
  const rowOnOtherSource = !!full?.reading_history && full.reading_history.source_slug !== full.source_slug;
  const pageLatest = full?.latest_available_chapter ?? null;
  const pageTarget = pageLatest && full ? { sourceSlug: full.source_slug, chapterNumber: pageLatest.chapter_id } : null;
  return (
    <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 1 }}>
      <Typography 
        variant="h3" 
        gutterBottom 
        sx={{ 
          color: 'common.white',
          textShadow: '0 2px 4px rgba(0,0,0,0.2)',
          fontWeight: 700,
        }}
      >
        {source.title}
        {source.is_adult && (
          // Always shown (unlike the cover badge, which only shows while blurred).
          <Tooltip
            title={adultTags.length ? t('sourceDetail.adultTagsReason', { tags: adultTags.join(', ') }) : ''}
          >
            <Chip
              label={t('sourceDetail.adultNote')}
              color="warning"
              size="small"
              sx={{ ml: 1.5, verticalAlign: 'middle', fontWeight: 'bold' }}
            />
          </Tooltip>
        )}
      </Typography>
      {isAuthenticated && (
        <Box sx={{ display: 'flex', gap: 0.5, flexShrink: 0 }}>
          <Tooltip title={isBookmarked ? t('novelActions.removeBookmark') : t('novelActions.bookmark')}>
            <IconButton
              onClick={onToggleBookmark}
              disabled={bookmarking || !novelSlug}
              sx={{
                color: 'common.white',
                bgcolor: alpha(theme.palette.common.black, 0.3),
                '&:hover': { bgcolor: alpha(theme.palette.common.black, 0.5) },
              }}
            >
              {isBookmarked ? <BookmarkIcon /> : <BookmarkBorderIcon />}
            </IconButton>
          </Tooltip>
          <Tooltip title={t('novelActions.addToReadingList')}>
            <IconButton
              onClick={onAddToList}
              disabled={!source.novel_id}
              sx={{
                color: 'common.white',
                bgcolor: alpha(theme.palette.common.black, 0.3),
                '&:hover': { bgcolor: alpha(theme.palette.common.black, 0.5) },
              }}
            >
              <PlaylistAddIcon />
            </IconButton>
          </Tooltip>
          {novel && full && (
            <MarkAsReadButton
              novel={{
                ...novel,
                slug: novelSlug ?? novel.slug,
                reading_history: full.reading_history,
                suggested_source: full,
              }}
              target={rowOnOtherSource ? pageTarget : undefined}
              onMarkAsRead={() =>
                setSource(prev =>
                  isFullSource(prev) && prev.reading_history
                    ? {
                        ...prev,
                        reading_history: {
                          ...prev.reading_history,
                          source_slug: prev.source_slug,
                          source_name: prev.source_name,
                          current_chapter: prev.latest_available_chapter ?? prev.reading_history.source_latest_chapter ?? prev.reading_history.current_chapter,
                          position: 1,
                          resume: null,
                          unread_chapters: 0,
                        },
                      }
                    : prev
                )
              }
              customSx={{ position: 'static', zIndex: 'auto', color: 'common.white' }}
            />
          )}
        </Box>
      )}
    </Box>
  );
};

export default SourceTitleBar;
