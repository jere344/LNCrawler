import { useState, useEffect } from 'react';
import { Box, Typography, Divider, CircularProgress } from '@mui/material';
import CommentForm from './CommentForm';
import CommentList from './CommentList';
import { novelService } from '../../services/api';

interface CommentSectionProps {
  novelSlug?: string;
  chapterData?: {
    novelSlug: string;
    sourceSlug: string;
    chapterNumber: number;
  };
  title: string;
}

const CommentSection = ({ novelSlug, chapterData, title }: CommentSectionProps) => {
  const [comments, setComments] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const isChapterComments = !!chapterData;
  
  useEffect(() => {
    const fetchComments = async () => {
      setLoading(true);
      setError(null);
      
      try {
        let fetchedComments;
        
        if (isChapterComments && chapterData) {
          fetchedComments = await novelService.getChapterComments(
            chapterData.novelSlug,
            chapterData.sourceSlug,
            chapterData.chapterNumber
          );
        } else if (novelSlug) {
          fetchedComments = await novelService.getNovelComments(novelSlug);
        } else {
          throw new Error('Either novelSlug or chapterData must be provided');
        }
        
        setComments(fetchedComments);
      } catch (err) {
        console.error('Failed to fetch comments:', err);
        setError('Failed to load comments. Please try refreshing the page.');
      } finally {
        setLoading(false);
      }
    };
    
    fetchComments();
  }, [novelSlug, chapterData, isChapterComments]);
  
  const handleAddComment = async (commentData: { 
    author_name: string; 
    message: string; 
    contains_spoiler: boolean; 
  }) => {
    try {
      let newComment;
      
      if (isChapterComments && chapterData) {
        newComment = await novelService.addChapterComment(
          chapterData.novelSlug,
          chapterData.sourceSlug,
          chapterData.chapterNumber,
          commentData
        );
      } else if (novelSlug) {
        newComment = await novelService.addNovelComment(novelSlug, commentData);
      } else {
        throw new Error('Either novelSlug or chapterData must be provided');
      }
      
      // Add the new comment to the list
      setComments(prev => [newComment, ...prev]);
    } catch (err) {
      console.error('Failed to add comment:', err);
      throw err; // Re-throw the error so the CommentForm can handle it
    }
  };
  
  const handleAddReply = async (parentId: string, commentData: { 
    author_name: string; 
    message: string; 
    contains_spoiler: boolean; 
    parent_id: string;
  }) => {
    try {
      let newReply;
      
      if (isChapterComments && chapterData) {
        newReply = await novelService.addChapterComment(
          chapterData.novelSlug,
          chapterData.sourceSlug,
          chapterData.chapterNumber,
          commentData
        );
      } else if (novelSlug) {
        newReply = await novelService.addNovelComment(novelSlug, commentData);
      } else {
        throw new Error('Either novelSlug or chapterData must be provided');
      }
      
      // Find the parent comment and add the reply to it
      // Note: This is a simplified approach. In a real app, you might want to refetch all comments
      // This approach keeps the UI updated without a full refetch
      setComments(prevComments => {
        // Function to recursively find and update the comment with the new reply
        const updateCommentWithReply = (comments: any[]): any[] => {
          return comments.map(comment => {
            if (comment.id === parentId) {
              // Add the reply to this comment
              return {
                ...comment,
                replies: [...(comment.replies || []), newReply],
                has_replies: true
              };
            }
            
            // If this comment has replies, check them too
            if (comment.replies && comment.replies.length > 0) {
              return {
                ...comment,
                replies: updateCommentWithReply(comment.replies)
              };
            }
            
            return comment;
          });
        };
        
        return updateCommentWithReply(prevComments);
      });
    } catch (err) {
      console.error('Failed to add reply:', err);
      throw err;
    }
  };

  return (
    <Box sx={{ mt: 4, mb: 6 }}>
      <Typography variant="h5" gutterBottom>
        {title}
      </Typography>
      
      <Divider sx={{ mb: 3 }} />
      
      <CommentForm onSubmit={handleAddComment} />
      
      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
          <CircularProgress />
        </Box>
      ) : error ? (
        <Typography color="error" sx={{ my: 2 }}>
          {error}
        </Typography>
      ) : (
        <CommentList 
          comments={comments}
          showCommentType={!isChapterComments} // Only show comment types in novel comments view
          emptyMessage="No comments yet. Be the first to comment!"
          showOtherSourceWarning={isChapterComments} // Only show warning for chapter comments
          onAddReply={handleAddReply}
        />
      )}
    </Box>
  );
};

export default CommentSection;
