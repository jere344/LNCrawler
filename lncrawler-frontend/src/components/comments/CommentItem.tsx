import { useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Chip,
  Button,
  IconButton,
  Tooltip,
  Avatar,
} from '@mui/material';
import ReplyIcon from '@mui/icons-material/Reply';
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import ArrowRightIcon from '@mui/icons-material/ArrowRight';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ThumbUpAltOutlinedIcon from '@mui/icons-material/ThumbUpAltOutlined';
import ThumbDownAltOutlinedIcon from '@mui/icons-material/ThumbDownAltOutlined';
import ThumbUpAltIcon from '@mui/icons-material/ThumbUpAlt';
import ThumbDownAltIcon from '@mui/icons-material/ThumbDownAlt';

import CommentForm from './CommentForm';
import { commentService } from '../../services/api';
import { Comment as IComment } from '@models/comments_types';
import { getChapterNameWithNumber } from '@utils/Misc';

interface CommentItemProps {
  comment: IComment;
  depth?: number;
  onAddReply?: (commentData: any) => Promise<void>;
  fromOtherSource?: boolean;
}

const CommentItem = ({
  comment,
  depth = 0,
  onAddReply,
  fromOtherSource = false,
}: CommentItemProps) => {
  const [isSpoilerRevealed, setSpoilerRevealed] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isReplying, setIsReplying] = useState(false);
  const [votes, setVotes] = useState({ upvotes: comment.upvotes, downvotes: comment.downvotes });
  const [currentVote, setCurrentVote] = useState<'up' | 'down' | null>(comment.user_vote || null);
  const [isVoting, setIsVoting] = useState(false);
  
  const hasReplies = comment.replies && comment.replies.length > 0;

  // Determine the name to display
  // Prioritize live username if the user is authenticated and username is provided
  // Otherwise, fall back to the author_name (historical or anonymous)
  const displayName = (comment.user != undefined && comment.user.username) ? comment.user.username : comment.author_name;

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
      await onAddReply({
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

  return (
    <Box sx={{ mb: 2 }}>
      <Paper 
        elevation={1} 
        sx={{ 
          p: 2, 
          bgcolor: fromOtherSource ? 'action.hover' : 'background.paper',
          borderLeft: depth > 0 ? '3px solid #9c27b0' : 'none', 
        }}
      >
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            {/* Show avatar only if it's an authenticated user's comment and they have a profile pic */}
            {comment.user != undefined && comment.user.profile_pic && (
              <Avatar 
                alt={displayName} // Use determined displayName
                src={comment.user.profile_pic} 
                sx={{ width: 24, height: 24, mr: 1 }} 
              />
            )}
            {/* Show initial-based avatar if authenticated user but no profile pic */}
            {comment.user != undefined && !comment.user.profile_pic && (
              <Avatar sx={{ width: 24, height: 24, mr: 1, bgcolor: 'primary.main' }}>
                {displayName ? displayName.charAt(0).toUpperCase() : '?'}
              </Avatar>
            )}
            <Typography variant="subtitle1" fontWeight="bold">
              {displayName}
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
        
        {comment.type && (
          <Box sx={{ mb: 1 }}>
            {comment.type === 'novel' ? (
              <Chip size="small" label="Novel Comment" color="primary" variant="outlined" />
            ) : (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Chip size="small" label={getChapterNameWithNumber(comment.chapter_title, comment.chapter_id)} color="secondary" variant="outlined" />
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
              onAddReply={onAddReply}
              fromOtherSource={fromOtherSource}
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
