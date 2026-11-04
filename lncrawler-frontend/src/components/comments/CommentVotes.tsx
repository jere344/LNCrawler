import { Box, IconButton, Tooltip, Typography } from '@mui/material';
import ThumbUpAltOutlinedIcon from '@mui/icons-material/ThumbUpAltOutlined';
import ThumbDownAltOutlinedIcon from '@mui/icons-material/ThumbDownAltOutlined';
import ThumbUpAltIcon from '@mui/icons-material/ThumbUpAlt';
import ThumbDownAltIcon from '@mui/icons-material/ThumbDownAlt';
import { useTranslation } from 'react-i18next';
import type { CommentVote } from './useCommentVote';

interface CommentVotesProps {
  votes: CommentVote;
}

// Upvote and downvote buttons with their counts, driven by useCommentVote
const CommentVotes = ({ votes }: CommentVotesProps) => {
  const { t } = useTranslation();

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Tooltip title={t('novelSources.upvote')}>
        <IconButton
          size="small"
          onClick={() => votes.vote('up')}
          disabled={votes.isVoting}
          color={votes.currentVote === 'up' ? "primary" : "default"}
        >
          {votes.currentVote === 'up' ? <ThumbUpAltIcon /> : <ThumbUpAltOutlinedIcon />}
        </IconButton>
      </Tooltip>
      <Typography variant="body2">{votes.upvotes}</Typography>

      <Tooltip title={t('novelSources.downvote')}>
        <IconButton
          size="small"
          onClick={() => votes.vote('down')}
          disabled={votes.isVoting}
          color={votes.currentVote === 'down' ? "secondary" : "default"}
        >
          {votes.currentVote === 'down' ? <ThumbDownAltIcon /> : <ThumbDownAltOutlinedIcon />}
        </IconButton>
      </Tooltip>
      <Typography variant="body2">{votes.downvotes}</Typography>
    </Box>
  );
};

export default CommentVotes;
