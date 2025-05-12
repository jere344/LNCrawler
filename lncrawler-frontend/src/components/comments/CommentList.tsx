import { useState } from 'react';
import {
  Box,
  Typography,
  Alert,
} from '@mui/material';
import CommentItem from './CommentItem';

interface Comment {
  id: string;
  author_name: string;
  message: string;
  contains_spoiler: boolean;
  created_at: string;
  from_other_source?: boolean;
  source_name?: string;
  type?: 'novel' | 'chapter';
  chapter_title?: string;
  chapter_id?: number;
  source_slug?: string;
  replies?: Comment[];
  has_replies?: boolean;
}

interface CommentListProps {
  comments: Comment[];
  showCommentType?: boolean;
  emptyMessage?: string;
  showOtherSourceWarning?: boolean;
  onAddReply?: (parentId: string, commentData: { 
    author_name: string; 
    message: string; 
    contains_spoiler: boolean;
    parent_id: string;
  }) => Promise<void>;
}

const CommentList = ({
  comments,
  showCommentType = false,
  emptyMessage = 'No comments yet. Be the first to comment!',
  showOtherSourceWarning = false,
  onAddReply,
}: CommentListProps) => {
  // Add debugging
  console.log(`CommentList rendering with ${comments.length} comments, onAddReply available: ${!!onAddReply}`);

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
      {showOtherSourceWarning && comments.some(c => c.from_other_source) && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Some comments below were posted for different sources. Sources may use different chapter numbering so there may be spoilers or seemingly irrelevant comments.
        </Alert>
      )}

      {comments.map(comment => (
        <CommentItem
          key={comment.id}
          comment={comment}
          showCommentType={showCommentType}
          onAddReply={onAddReply} // Ensure this is correctly passed
        />
      ))}
    </Box>
  );
};

export default CommentList;
