import {
  Box,
  Typography,
  Alert,
} from '@mui/material';
import CommentItem from './CommentItem';
import { Comment, CommentFormData } from '@models/comments_types';
import { useTranslation } from 'react-i18next';

interface CommentListProps {
  comments: Comment[];
  onAddReply?: (commentData: CommentFormData) => Promise<void>;
  currentSource?: string;
}

const CommentList = ({
  comments,
  onAddReply,
  currentSource,
}: CommentListProps) => {
  const { t } = useTranslation();
  const emptyMessage = t('comments.noComments');

  if (comments.length === 0) {
    return (
      <Box sx={{ py: 2, textAlign: 'center' }}>
        <Typography sx={{
          color: "text.secondary"
        }}>
          {emptyMessage}
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      {currentSource && comments.some(comment => comment.source_slug !== currentSource) && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {t('comments.mixedSourcesWarning')}
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
