import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { commentService } from '@services/comment.service';
import { getApiErrorMessage } from '@utils/apiError';
import { Comment } from '@models/comments_types';

// Inline edit state for a comment: draft message and spoiler flag, saving and errors
export const useCommentEdit = (comment: Comment, onSaved: (updated: Comment) => void) => {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [message, setMessage] = useState(comment.message);
  const [containsSpoiler, setContainsSpoiler] = useState(comment.contains_spoiler);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = () => {
    setIsEditing(true);
    setMessage(comment.message);
    setContainsSpoiler(comment.contains_spoiler);
  };

  const cancel = () => {
    setIsEditing(false);
    setError(null);
  };

  const save = async () => {
    if (!message.trim()) {
      setError(t('comments.empty'));
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const updatedComment = await commentService.editComment(comment.id, {
        message,
        contains_spoiler: containsSpoiler
      });

      onSaved({
        ...comment,
        message: updatedComment.message,
        contains_spoiler: updatedComment.contains_spoiler,
        edited: true,
      });

      setIsEditing(false);
    } catch (err) {
      console.error('Failed to edit comment:', err);
      setError(getApiErrorMessage(err, t, 'comments.editFailed'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return {
    isEditing,
    start,
    cancel,
    message,
    setMessage,
    containsSpoiler,
    setContainsSpoiler,
    isSubmitting,
    error,
    setError,
    save,
  };
};

export type CommentEdit = ReturnType<typeof useCommentEdit>;
