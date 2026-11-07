import { Box, Button, ButtonBase, Chip, IconButton, Typography, type Theme } from '@mui/material';
import { useTranslation } from 'react-i18next';
import ReplyIcon from '@mui/icons-material/Reply';
import EditIcon from '@mui/icons-material/Edit';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutlineOutlined';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import type { Comment } from '@models/comments_types';
import { useAuth } from '@context/AuthContext';
import { usePrefersReducedMotion } from '@components/reader/hooks/usePrefersReducedMotion';
import { TOUCH_MIN_HEIGHT, TOUCH_TARGET } from '@components/reader/touchTarget';
import DirectionalIcon from '@components/reader/DirectionalIcon';
import CommentAuthor from './CommentAuthor';
import CommentDate from './CommentDate';
import CommentMessage from './CommentMessage';
import CommentEditForm from './CommentEditForm';
import CommentVotes from './CommentVotes';
import { useCommentVote } from './useCommentVote';
import { useCommentEdit } from './useCommentEdit';
import { HIGHLIGHT_MS } from './useCommentListScroll';
import { countDescendants } from './commentTree';
import { commentAuthorName, isOwnComment } from './commentAuthor';

// Replies shown under a comment before "more replies" is offered
const PREVIEW_REPLIES = 2;
// The thread line sits under the centre of the author's avatar
const REPLY_INDENT = '13px';
const REPLY_PADDING = '12px';
// The text starts under the author's name, past the avatar
const BODY_INDENT = '36px';
// The actions line up with the text, a little to the start of it
const ACTIONS_INDENT = '28px';

// The highlight fades from the selected colour to nothing, through a named keyframes that every highlighted comment shares
const highlightSx = (theme: Theme) => ({
  '@keyframes commentHighlightFade': {
    from: { backgroundColor: theme.palette.action.selected },
    to: { backgroundColor: 'transparent' },
  },
  animation: `commentHighlightFade ${HIGHLIGHT_MS}ms ease-out`,
});

interface ThreadCommentProps {
  comment: Comment;
  // Levels below the top of the thread view; the top is 0
  depth: number;
  maxDepth: number;
  // The source the thread is read from: comments from another source are marked
  currentSource?: string;
  // A chapter comment on a novel page names its chapter and source
  showChapterLabel: boolean;
  // Comment ids collapsed to a single row
  hidden: Set<string>;
  // Comment ids whose replies are all shown, past the preview
  expanded: Set<string>;
  highlightId: string | null;
  onToggleHidden: (id: string) => void;
  onShowAll: (id: string) => void;
  onContinue: (id: string) => void;
  onReply: (comment: Comment) => void;
  onUpdate: (comment: Comment) => void;
}

// A comment with its replies under it, recursively. Deeper replies open as a thread of their own.
const ThreadComment = ({
  comment,
  depth,
  maxDepth,
  currentSource,
  showChapterLabel,
  hidden,
  expanded,
  highlightId,
  onToggleHidden,
  onShowAll,
  onContinue,
  onReply,
  onUpdate,
}: ThreadCommentProps) => {
  const { t } = useTranslation();
  const reducedMotion = usePrefersReducedMotion();
  const { isAuthenticated, user } = useAuth();
  const votes = useCommentVote(comment, onUpdate);
  const edit = useCommentEdit(comment, onUpdate);

  const name = commentAuthorName(comment);
  const canEdit = isAuthenticated && isOwnComment(comment, user);
  const showSourceChip = !!currentSource && !!comment.source_slug && comment.source_slug !== currentSource;
  // Only top-level comments name their chapter: a reply is always on its parent's chapter
  const chapterOrigin = showChapterLabel && depth === 0 && comment.type === 'chapter';
  const isHidden = hidden.has(comment.id);
  const replies = comment.replies ?? [];
  const descendants = countDescendants(comment);
  const shownReplies = expanded.has(comment.id) ? replies : replies.slice(0, PREVIEW_REPLIES);
  const isHighlighted = comment.id === highlightId;

  return (
    <Box
      component="article"
      id={`comment-${comment.id}`}
      sx={[
        {
          paddingBlockStart: depth === 0 ? '12px' : '10px',
          paddingBlockEnd: depth === 0 ? '12px' : 0,
          borderBottom: depth === 0 ? 1 : 0,
          borderColor: 'divider',
        },
        isHighlighted && !reducedMotion && highlightSx,
      ]}
    >
      {isHidden ? (
        <ButtonBase
          component="div"
          aria-expanded={false}
          aria-label={t('readerComments.expandThread', { name })}
          onClick={() => onToggleHidden(comment.id)}
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            width: '100%',
            minHeight: TOUCH_MIN_HEIGHT,
            px: 1,
            borderRadius: '8px',
            justifyContent: 'flex-start',
            textAlign: 'start',
            '&:hover': { bgcolor: 'action.hover' },
          }}
        >
          <Box sx={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            <CommentAuthor comment={comment} dense plain />
            <CommentDate comment={comment} />
            {descendants > 0 && (
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {t('readerComments.repliesHidden', { count: descendants })}
              </Typography>
            )}
          </Box>
          <AddCircleOutlineIcon fontSize="small" sx={{ flex: 'none', color: 'text.secondary' }} />
        </ButtonBase>
      ) : (
        <>
          <CommentAuthor comment={comment} dense>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', minWidth: 0, marginInlineStart: 1 }}>
              {chapterOrigin && (
                <Chip
                  size="small"
                  variant="outlined"
                  color="secondary"
                  label={t('comments.postedAt', { chapter: comment.chapter_display_title })}
                  sx={{ maxWidth: '100%', minWidth: 0 }}
                />
              )}
              {chapterOrigin && (
                <Typography variant="body2" noWrap sx={{ minWidth: 0, color: 'text.secondary' }}>
                  {t('comments.fromSource', { source: comment.source_name })}
                </Typography>
              )}
              {!chapterOrigin && showSourceChip && (
                <Chip
                  size="small"
                  variant="outlined"
                  color="secondary"
                  label={t('readerComments.fromSource', { source: comment.source_name })}
                  sx={{ maxWidth: '100%', minWidth: 0 }}
                />
              )}
              <CommentDate comment={comment} />
            </Box>
          </CommentAuthor>

          <Box sx={{ paddingInlineStart: BODY_INDENT }}>
            {edit.isEditing ? (
              <CommentEditForm edit={edit} />
            ) : (
              <CommentMessage message={comment.message} containsSpoiler={comment.contains_spoiler} />
            )}
          </Box>

          {!edit.isEditing && (
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 1,
                marginBlockStart: '4px',
                paddingInlineStart: ACTIONS_INDENT,
              }}
            >
              <CommentVotes votes={votes} />
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <Button size="small" startIcon={<ReplyIcon />} onClick={() => onReply(comment)} sx={{ minHeight: TOUCH_MIN_HEIGHT }}>
                  {t('comments.reply')}
                </Button>
                {canEdit && (
                  <IconButton
                    onClick={() => edit.start()}
                    aria-label={t('comments.editTooltip')}
                    sx={TOUCH_TARGET}
                  >
                    <EditIcon fontSize="small" />
                  </IconButton>
                )}
              </Box>
            </Box>
          )}

          {replies.length > 0 && depth >= maxDepth && (
            <Box sx={{ marginInlineStart: REPLY_INDENT, paddingInlineStart: REPLY_PADDING }}>
              <Button
                size="small"
                // Found by id when the thread is closed, so focus goes back to it
                data-thread-id={comment.id}
                onClick={() => onContinue(comment.id)}
                endIcon={<DirectionalIcon><ChevronRightIcon /></DirectionalIcon>}
                sx={{ minHeight: TOUCH_MIN_HEIGHT }}
              >
                {t('readerComments.continueThread', { count: descendants })}
              </Button>
            </Box>
          )}

          {replies.length > 0 && depth < maxDepth && (
            <Box sx={{ position: 'relative', marginInlineStart: REPLY_INDENT, paddingInlineStart: REPLY_PADDING }}>
              {/* The thread line: a click collapses the replies under this comment */}
              <ButtonBase
                aria-label={t('readerComments.collapseThread', { name })}
                aria-expanded
                onClick={() => onToggleHidden(comment.id)}
                sx={{
                  position: 'absolute',
                  insetInlineStart: '-8px',
                  top: 0,
                  bottom: 0,
                  width: 18,
                  '&::before': {
                    content: '""',
                    position: 'absolute',
                    insetInlineStart: '8px',
                    top: 0,
                    bottom: 0,
                    width: 2,
                    bgcolor: 'divider',
                  },
                  '&:hover::before, &.Mui-focusVisible::before': { bgcolor: 'primary.main', width: 3 },
                }}
              />

              {shownReplies.map((reply) => (
                <ThreadComment
                  key={reply.id}
                  comment={reply}
                  depth={depth + 1}
                  maxDepth={maxDepth}
                  currentSource={currentSource}
                  showChapterLabel={showChapterLabel}
                  hidden={hidden}
                  expanded={expanded}
                  highlightId={highlightId}
                  onToggleHidden={onToggleHidden}
                  onShowAll={onShowAll}
                  onContinue={onContinue}
                  onReply={onReply}
                  onUpdate={onUpdate}
                />
              ))}

              {shownReplies.length < replies.length && (
                <Button size="small" onClick={() => onShowAll(comment.id)} sx={{ minHeight: TOUCH_MIN_HEIGHT }}>
                  {t('readerComments.moreReplies', { count: replies.length - shownReplies.length })}
                </Button>
              )}
            </Box>
          )}
        </>
      )}
    </Box>
  );
};

export default ThreadComment;
