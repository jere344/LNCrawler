import { Box, ButtonBase, Divider, Paper, Typography } from '@mui/material';
import CommentIcon from '@mui/icons-material/Comment';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { useTranslation } from 'react-i18next';
import type { CommentPreview } from '@models/comments_types';
import DirectionalIcon from '../DirectionalIcon';
import { TOUCH_MIN_HEIGHT } from '../touchTarget';

interface ChapterCommentsCardProps {
  count: number;
  chapterLabel: string;
  topComment: CommentPreview | null;
  onOpen: (opts?: { compose?: boolean }) => void;
}

// Summary of the chapter's comments under the text: opens the comments panel, or its composer
const ChapterCommentsCard = ({ count, chapterLabel, topComment, onOpen }: ChapterCommentsCardProps) => {
  const { t } = useTranslation();

  return (
    <Paper variant="outlined" sx={{ borderRadius: '14px', overflow: 'hidden' }}>
      <ButtonBase
        // With no comment yet, the first tap goes straight to the composer
        onClick={() => onOpen(count === 0 ? { compose: true } : undefined)}
        sx={{ display: 'block', width: '100%', textAlign: 'start', p: 1.5 }}
      >
        {/* Spans only: a button takes phrasing content */}
        <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CommentIcon fontSize="small" sx={{ opacity: 0.75 }} />
          <Typography component="span" variant="subtitle2" sx={{ display: 'block', flex: 1, minWidth: 0 }}>
            {t('readerComments.cardTitle', { count, chapter: chapterLabel })}
          </Typography>
          <DirectionalIcon>
            <ChevronRightIcon sx={{ color: 'text.secondary' }} />
          </DirectionalIcon>
        </Box>

        {topComment && (
          <Typography
            component="span"
            variant="body2"
            color="text.secondary"
            sx={{ mt: 1, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
          >
            <Box component="span" sx={{ fontWeight: 'bold', color: 'text.primary' }}>{topComment.author_name}</Box>{' '}
            {/* A spoiler, or a comment whose text is hidden (no message), shows the spoiler label */}
            {topComment.contains_spoiler || topComment.message === null
              ? <Box component="span" sx={{ fontStyle: 'italic' }}>{t('readerComments.cardSpoiler')}</Box>
              : `“${topComment.message}”`}
          </Typography>
        )}

        {count === 0 && (
          <Typography component="span" variant="body2" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
            {t('readerComments.cardEmpty')}
          </Typography>
        )}
      </ButtonBase>

      {count > 0 && (
        <>
          <Divider />
          <ButtonBase
            onClick={() => onOpen({ compose: true })}
            sx={{ display: 'flex', width: '100%', minHeight: TOUCH_MIN_HEIGHT, px: 2, justifyContent: 'flex-start', textAlign: 'start', color: 'text.secondary', typography: 'body2' }}
          >
            {t('readerComments.cardAdd')}
          </ButtonBase>
        </>
      )}
    </Paper>
  );
};

export default ChapterCommentsCard;
