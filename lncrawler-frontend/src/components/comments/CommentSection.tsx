import { useState, useEffect } from 'react';
import { Box, Typography, Divider, CircularProgress } from '@mui/material';
import CommentForm from './CommentForm';
import CommentList from './CommentList';
import { novelService } from '../../services/api';
import { boardService } from '../../services/board.service';

interface CommentSectionProps {
  novelSlug?: string;
  chapterData?: {
    novelSlug: string;
    sourceSlug: string;
    chapterNumber: number;
  };
  boardSlug?: string;
  title: string;
}

const CommentSection = ({ novelSlug, chapterData, boardSlug, title }: CommentSectionProps) => {
  const [comments, setComments] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const isChapterComments = !!chapterData;
  const isBoardComments = !!boardSlug;
  
  useEffect(() => {
    const fetchComments = async () => {
      setLoading(true);
      setError(null);
      
      try {
        let fetchedComments;
        
        if (isBoardComments && boardSlug) {
          fetchedComments = await boardService.getBoardComments(boardSlug);
        } else if (isChapterComments && chapterData) {
          fetchedComments = await novelService.getChapterComments(
            chapterData.novelSlug,
            chapterData.sourceSlug,
            chapterData.chapterNumber
          );
        } else if (novelSlug) {
          fetchedComments = await novelService.getNovelComments(novelSlug);
        } else {
          throw new Error('Either novelSlug, chapterData, or boardSlug must be provided');
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
  }, [novelSlug, chapterData, boardSlug, isChapterComments, isBoardComments]);
  
  const handleAddComment = async (commentData: { 
    author_name: string; 
    message: string; 
    contains_spoiler: boolean; 
    parent_id?: string;
  }) => {
    try {
      if (isBoardComments && boardSlug) {
        await boardService.addBoardComment(boardSlug, commentData);
        // Refetch all comments to ensure consistency
        const updatedComments = await boardService.getBoardComments(boardSlug);
        setComments(updatedComments);
      } else if (isChapterComments && chapterData) {
        await novelService.addChapterComment(
          chapterData.novelSlug,
          chapterData.sourceSlug,
          chapterData.chapterNumber,
          commentData
        );
        // Refetch all comments to ensure consistency
        const updatedComments = await novelService.getChapterComments(
          chapterData.novelSlug,
          chapterData.sourceSlug,
          chapterData.chapterNumber
        );
        setComments(updatedComments);
      } else if (novelSlug) {
        await novelService.addNovelComment(novelSlug, commentData);
        // Refetch all comments to ensure consistency
        const updatedComments = await novelService.getNovelComments(novelSlug);
        setComments(updatedComments);
      } else {
        throw new Error('Either novelSlug, chapterData, or boardSlug must be provided');
      }
    } catch (err) {
      console.error('Failed to add comment:', err);
      throw err; // Re-throw the error so the CommentForm can handle it
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
          onAddReply={handleAddComment}
          currentSource={chapterData?.sourceSlug}
        />
      )}
    </Box>
  );
};

export default CommentSection;
