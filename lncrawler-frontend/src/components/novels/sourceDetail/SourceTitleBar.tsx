import type { Dispatch, SetStateAction } from 'react';
import { Box, Chip, IconButton, Tooltip, Typography, alpha, useTheme } from '@mui/material';
import { useTranslation } from 'react-i18next';
import BookmarkBorderIcon from '@mui/icons-material/BookmarkBorder';
import BookmarkIcon from '@mui/icons-material/Bookmark';
import PlaylistAddIcon from '@mui/icons-material/PlaylistAdd';
import MarkAsReadButton from '../../common/MarkAsReadButton';
import { NovelFromSource as ISourceDetail, NovelDetail as INovelDetail, Novel as INovel } from '@models/novels_types';

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
  source: ISourceDetail;
  novel: INovelDetail | null;
  novelSlug: string | undefined;
  isAuthenticated: boolean;
  isBookmarked: boolean;
  bookmarking: boolean;
  onToggleBookmark: () => void;
  onAddToList: () => void;
  setSource: Dispatch<SetStateAction<ISourceDetail | null>>;
}) => {
  const { t } = useTranslation();
  const theme = useTheme();
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
            title={source.adult_tags?.length ? t('sourceDetail.adultTagsReason', { tags: source.adult_tags.join(', ') }) : ''}
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
              disabled={!source?.novel_id}
              sx={{
                color: 'common.white',
                bgcolor: alpha(theme.palette.common.black, 0.3),
                '&:hover': { bgcolor: alpha(theme.palette.common.black, 0.5) },
              }}
            >
              <PlaylistAddIcon />
            </IconButton>
          </Tooltip>
          {novel && (
            <MarkAsReadButton
              novel={{
                ...novel,
                slug: novelSlug ?? novel.slug,
                reading_history: source.reading_history,
                prefered_source: source,
              } as unknown as INovel}
              onMarkAsRead={() =>
                setSource(prev =>
                  prev?.reading_history
                    ? {
                        ...prev,
                        reading_history: {
                          ...prev.reading_history,
                          last_read_chapter: prev.reading_history.source_latest_chapter ?? prev.reading_history.last_read_chapter,
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
