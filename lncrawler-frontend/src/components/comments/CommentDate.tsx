import { Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { Comment } from '@models/comments_types';
import { formatDateTime } from '@utils/Misc';

interface CommentDateProps {
  comment: Comment;
}

// Creation date of a comment, followed by an "edited" mark when it was changed
const CommentDate = ({ comment }: CommentDateProps) => {
  const { t, i18n } = useTranslation();

  return (
    <Typography variant="body2" sx={{
      color: "text.secondary"
    }}>
      {formatDateTime(comment.created_at, i18n.language)}
      {comment.edited && (
        <Typography
          component="span"
          variant="caption"
          sx={{
            color: "text.secondary",
            marginInlineStart: 1
          }}>
          {t('comments.edited')}
        </Typography>
      )}
    </Typography>
  );
};

export default CommentDate;
