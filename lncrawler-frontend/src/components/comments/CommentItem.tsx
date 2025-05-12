import { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  Chip,
  Button,
  IconButton,
  Divider,
  Tooltip,
} from '@mui/material';
import ReplyIcon from '@mui/icons-material/Reply';
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import ArrowRightIcon from '@mui/icons-material/ArrowRight';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ThumbUpAltOutlinedIcon from '@mui/icons-material/ThumbUpAltOutlined';
import ThumbDownAltOutlinedIcon from '@mui/icons-material/ThumbDownAltOutlined';
import ThumbUpAltIcon from '@mui/icons-material/ThumbUpAlt'; // For filled state
import ThumbDownAltIcon from '@mui/icons-material/ThumbDownAlt'; // For filled state

import CommentForm from './CommentForm';
import { commentService } from '../../services/api'; // Import commentService

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
  upvotes: number; // Added
  downvotes: number; // Added
  vote_score: number; // Added
}

interface CommentItemProps {
  comment: Comment;
  depth?: number;
  showCommentType?: boolean;
  onAddReply?: (parentId: string, commentData: any) => Promise<void>;
}

const CommentItem = ({
  comment,
  depth = 0,
  showCommentType = false,
  onAddReply,
}: CommentItemProps) => {
  const [isSpoilerRevealed, setSpoilerRevealed] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isReplying, setIsReplying] = useState(false);
  const [votes, setVotes] = useState({ upvotes: comment.upvotes, downvotes: comment.downvotes });
  const [currentVote, setCurrentVote] = useState<'up' | 'down' | null>(null); // Track user's vote on this comment
  const [isVoting, setIsVoting] = useState(false);
  
  const hasReplies = comment.replies && comment.replies.length > 0;

  // Format date to readable format
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('en-US', { 
      year: 'numeric', 
      month: 'short', 
      day: 'numeric',
      hour: 'numeric',
      minute: 'numeric'
    }).format(date);
  };
  
  const handleReplySubmit = async (data: any) => {
    if (onAddReply) {
      await onAddReply(comment.id, {
        ...data,
        parent_id: comment.id
      });
      setIsReplying(false);
    }
  };

  const handleVote = async (voteType: 'up' | 'down') => {
    if (isVoting) return;
    setIsVoting(true);
    try {
      // If current vote is the same as new vote, treat as unvoting (not standard, but can be implemented)
      // For now, API handles changing vote or new vote.
      // To prevent double voting or allow changing vote, the backend logic with update_or_create is key.
      const updatedCommentData = await commentService.voteComment(comment.id, voteType);
      setVotes({
        upvotes: updatedCommentData.upvotes,
        downvotes: updatedCommentData.downvotes,
      });
      setCurrentVote(voteType); 
    } catch (error) {
      console.error('Failed to vote on comment:', error);
      // Optionally, show an error message to the user
    } finally {
      setIsVoting(false);
    }
  };

  // For debugging
  console.log(`Rendering comment ${comment.id}, onAddReply available: ${!!onAddReply}`);

  return (
    <Box sx={{ mb: 2 }}>
      <Paper 
        elevation={1} 
        sx={{ 
          p: 2, 
          bgcolor: comment.from_other_source ? 'action.hover' : 'background.paper',
          borderLeft: depth > 0 ? '3px solid #9c27b0' : 'none',
        }}
      >
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Typography variant="subtitle1" fontWeight="bold">
              {comment.author_name}
              
              {comment.from_other_source && comment.source_name && (
                <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 1 }}>
                  (from {comment.source_name})
                </Typography>
              )}
            </Typography>
            
            {hasReplies && (
              <IconButton 
                size="small" 
                onClick={() => setIsCollapsed(!isCollapsed)}
                sx={{ ml: 1 }}
              >
                {isCollapsed ? <ArrowRightIcon /> : <ArrowDropDownIcon />}
              </IconButton>
            )}
          </Box>
          
          <Typography variant="body2" color="text.secondary">
            {formatDate(comment.created_at)}
          </Typography>
        </Box>
        
        {showCommentType && comment.type && (
          <Box sx={{ mb: 1 }}>
            {comment.type === 'novel' ? (
              <Chip size="small" label="Novel Comment" color="primary" variant="outlined" />
            ) : (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Chip size="small" label={`Chapter ${comment.chapter_id}: ${comment.chapter_title}`} color="secondary" variant="outlined" />
                <Typography variant="body2" color="text.secondary">
                  from {comment.source_name}
                </Typography>
              </Box>
            )}
          </Box>
        )}

        {/* Comment content section */}
        {comment.contains_spoiler ? (
          <Box sx={{ mt: 1 }}>
            <Typography 
              variant="body1" 
              onClick={() => setSpoilerRevealed(!isSpoilerRevealed)}
              sx={{ 
                whiteSpace: 'pre-wrap', 
                wordBreak: 'break-word',
                filter: isSpoilerRevealed ? 'none' : 'blur(5px)',
                cursor: 'pointer',
                transition: 'filter 0.2s',
                p: 1,
                borderLeft: '4px solid #f5c842',
                bgcolor: 'rgba(255, 244, 229, 0.2)',
                '&:hover': {
                  bgcolor: 'rgba(255, 244, 229, 0.5)',
                }
              }}
            >
              {comment.message}
            </Typography>
            {!isSpoilerRevealed && (
              <Typography 
                variant="caption" 
                color="warning.main" 
                sx={{ display: 'block', mt: 0.5, fontStyle: 'italic' }}
              >
                (spoiler)
              </Typography>
            )}
          </Box>
        ) : (
          <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {comment.message}
          </Typography>
        )}
        
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Tooltip title="Upvote">
              <IconButton 
                size="small" 
                onClick={() => handleVote('up')} 
                disabled={isVoting}
                color={currentVote === 'up' ? "primary" : "default"}
              >
                {currentVote === 'up' ? <ThumbUpAltIcon /> : <ThumbUpAltOutlinedIcon />}
              </IconButton>
            </Tooltip>
            <Typography variant="body2">{votes.upvotes}</Typography>
            
            <Tooltip title="Downvote">
              <IconButton 
                size="small" 
                onClick={() => handleVote('down')} 
                disabled={isVoting}
                color={currentVote === 'down' ? "secondary" : "default"}
              >
                {currentVote === 'down' ? <ThumbDownAltIcon /> : <ThumbDownAltOutlinedIcon />}
              </IconButton>
            </Tooltip>
            <Typography variant="body2">{votes.downvotes}</Typography>
          </Box>
+
          {onAddReply ? (
            <Button 
              variant="outlined"
              size="small" 
              startIcon={<ReplyIcon />} 
              onClick={() => setIsReplying(!isReplying)}
              color="primary"
              sx={{ borderRadius: 2 }}
            >
              {isReplying ? 'Cancel Reply' : 'Reply'}
            </Button>
          ) : (
            <Typography variant="caption" color="text.secondary">
              Replies disabled
            </Typography>
          )}
        </Box>
      </Paper>
      
      {/* Reply form */}
      {isReplying && (
        <Box sx={{ ml: 4, mt: 1, mb: 2 }}>
          <CommentForm 
            onSubmit={handleReplySubmit}
            isReply={true}
            parentAuthor={comment.author_name}
            onCancel={() => setIsReplying(false)}
          />
        </Box>
      )}
      
      {/* Render replies if not collapsed */}
      {hasReplies && !isCollapsed && (
        <Box sx={{ mt: 1, ml: 4 }}>
          {comment.replies!.map(reply => (
            <CommentItem 
              key={reply.id}
              comment={reply}
              depth={depth + 1}
              showCommentType={showCommentType}
              onAddReply={onAddReply}
            />
          ))}
        </Box>
      )}
      
      {/* Show collapsed replies indicator */}
      {hasReplies && isCollapsed && (
        <Button 
          sx={{ ml: 4, mt: 1 }}
          startIcon={<ExpandMoreIcon />}
          onClick={() => setIsCollapsed(false)}
          color="primary"
          size="small"
        >
          Show {comment.replies!.length} {comment.replies!.length === 1 ? 'reply' : 'replies'}
        </Button>
      )}
    </Box>
  );
};

export default CommentItem;
