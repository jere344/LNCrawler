import {
  Box,
  Typography,
  Alert,
} from '@mui/material';
import CommentItem from './CommentItem';
import { Comment } from '@models/comments_types';

interface CommentListProps {
  comments: Comment[];
  onAddReply?: (commentData: { 
    author_name: string; 
    message: string; 
    contains_spoiler: boolean;
    parent_id: string;
  }) => Promise<void>;
  currentSource?: string;
}

const CommentList = ({
  comments,
  onAddReply,
  currentSource,
}: CommentListProps) => {
  const emptyMessage = 'No comments yet. Be the first to comment!';

  if (comments.length === 0) {
    return (
      <Box sx={{ py: 2, textAlign: 'center' }}>
        <Typography color="text.secondary">
          {emptyMessage}
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      {currentSource && comments.some(comment => comment.source_slug !== currentSource) && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Some comments below were posted for different sources. Sources may use different chapter numbering so there may be spoilers or seemingly irrelevant comments.
        </Alert>
      )}

      {comments.map(comment => (
        <CommentItem
          key={comment.id}
          fromOtherSource={currentSource ? (comment.source_slug !== currentSource) : false}
          comment={comment}
          onAddReply={onAddReply}
        />
      ))}
    </Box>
  );
};

export default CommentList;
