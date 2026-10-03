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
  TextField,
  FormControlLabel,
  Checkbox,
  CircularProgress,
  Alert,
} from '@mui/material';
import ReplyIcon from '@mui/icons-material/Reply';
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import ArrowRightIcon from '@mui/icons-material/ArrowRight';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ThumbUpAltOutlinedIcon from '@mui/icons-material/ThumbUpAltOutlined';
import ThumbDownAltOutlinedIcon from '@mui/icons-material/ThumbDownAltOutlined';
import ThumbUpAltIcon from '@mui/icons-material/ThumbUpAlt';
import ThumbDownAltIcon from '@mui/icons-material/ThumbDownAlt';
import EditIcon from '@mui/icons-material/Edit';
import SaveIcon from '@mui/icons-material/Save';
import CancelIcon from '@mui/icons-material/Cancel';

import CommentForm from './CommentForm';
import { commentService, type ApiError } from '../../services/api';
import { Comment as IComment, CommentFormData } from '@models/comments_types';
import { getChapterLabel } from '@utils/Misc';
import { useAuth } from '../../context/AuthContext';
import { useTranslation } from 'react-i18next';

interface CommentItemProps {
  comment: IComment;
  depth?: number;
  onAddReply?: (commentData: CommentFormData) => Promise<void>;
  fromOtherSource?: boolean;
}

const CommentItem = ({
  comment,
  depth = 0,
  onAddReply,
  fromOtherSource = false,
}: CommentItemProps) => {
  const { isAuthenticated, user } = useAuth();
  const { t, i18n } = useTranslation();
  const [isSpoilerRevealed, setSpoilerRevealed] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isReplying, setIsReplying] = useState(false);
  const [votes, setVotes] = useState({ upvotes: comment.upvotes, downvotes: comment.downvotes });
  const [currentVote, setCurrentVote] = useState<'up' | 'down' | null>(comment.user_vote || null);
  const [isVoting, setIsVoting] = useState(false);
  
  // Edit state
  const [isEditing, setIsEditing] = useState(false);
  const [editMessage, setEditMessage] = useState(comment.message);
  const [editContainsSpoiler, setEditContainsSpoiler] = useState(comment.contains_spoiler);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  
  const hasReplies = comment.replies && comment.replies.length > 0;

  // Check if current user can edit this comment
  const canEdit = isAuthenticated && 
                 user && 
                 comment.user && 
                 user.username === comment.user.username;

  // Determine the name to display
  const displayName = (comment.user != undefined && comment.user.username) ? comment.user.username : comment.author_name;

  // Format date to readable format
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat(i18n.language, { 
      year: 'numeric', 
      month: 'short', 
      day: 'numeric',
      hour: 'numeric',
      minute: 'numeric'
    }).format(date);
  };
  
  const handleReplySubmit = async (data: CommentFormData) => {
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
      const updatedCommentData = await commentService.voteComment(comment.id, voteType);
      setVotes({
        upvotes: updatedCommentData.upvotes,
        downvotes: updatedCommentData.downvotes,
      });
      setCurrentVote(voteType); 
    } catch (error) {
      console.error('Failed to vote on comment:', error);
    } finally {
      setIsVoting(false);
    }
  };

  const handleEditStart = () => {
    setIsEditing(true);
    setEditMessage(comment.message);
    setEditContainsSpoiler(comment.contains_spoiler);
  };

  const handleEditCancel = () => {
    setIsEditing(false);
    setEditError(null);
  };

  const handleEditSave = async () => {
    if (!editMessage.trim()) {
      setEditError(t('comments.empty'));
      return;
    }

    setIsSubmitting(true);
    setEditError(null);

    try {
      const updatedComment = await commentService.editComment(comment.id, {
        message: editMessage,
        contains_spoiler: editContainsSpoiler
      });
      
      // Update local comment with new data
      comment.message = updatedComment.message;
      comment.contains_spoiler = updatedComment.contains_spoiler;
      comment.edited = true;
      
      setIsEditing(false);
    } catch (error) {
      const apiErr = error as ApiError;
      console.error('Failed to edit comment:', error);
      setEditError(apiErr?.response?.data?.error || t('comments.editFailed'));
    } finally {
      setIsSubmitting(false);
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
            <Typography variant="subtitle1" sx={{
              fontWeight: "bold"
            }}>
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
          
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body2" sx={{
              color: "text.secondary"
            }}>
              {formatDate(comment.created_at)}
              {comment.edited && (
                <Typography
                  component="span"
                  variant="caption"
                  sx={{
                    color: "text.secondary",
                    ml: 1
                  }}>
                  {t('comments.edited')}
                </Typography>
              )}
            </Typography>
            
            {canEdit && !isEditing && (
              <Tooltip title={t('comments.editTooltip')}>
                <IconButton size="small" onClick={handleEditStart}>
                  <EditIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
          </Box>
        </Box>
        
        {comment.type === 'board' ? (
          <Box sx={{ mb: 1 }}>
            <Chip size="small" label={t('comments.boardComment')} color="secondary" variant="outlined" />
          </Box>
        ) : comment.type && comment.type !== 'novel' ? (
          <Box sx={{ mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
            <Chip size="small" label={t('comments.postedAt', { chapter: getChapterLabel(t, comment.chapter_title, comment.chapter_id) })} color="secondary" variant="outlined" />
            <Typography variant="body2" sx={{
              color: "text.secondary"
            }}>
              {t('comments.fromSource', { source: comment.source_name })}
            </Typography>
          </Box>
        ) : null}

        {/* Comment content section - normal view or edit view */}
        {isEditing ? (
          <Box sx={{ mt: 2 }}>
            {editError && (
              <Alert severity="error" sx={{ mb: 2 }} onClose={() => setEditError(null)}>
                {editError}
              </Alert>
            )}
            
            <TextField
              fullWidth
              label={t('comments.editPlaceholder')}
              multiline
              rows={4}
              value={editMessage}
              onChange={(e) => setEditMessage(e.target.value)}
              disabled={isSubmitting}
            />
            
            <FormControlLabel
              control={
                <Checkbox 
                  checked={editContainsSpoiler}
                  onChange={(e) => setEditContainsSpoiler(e.target.checked)}
                  color="primary"
                />
              }
              label={t('comments.containsSpoilers')}
              sx={{ mt: 1 }}
            />
            
            <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
              <Button
                variant="contained"
                color="primary"
                startIcon={isSubmitting ? <CircularProgress size={20} color="inherit" /> : <SaveIcon />}
                onClick={handleEditSave}
                disabled={isSubmitting}
              >
                {t('common.save')}
              </Button>
              <Button
                variant="outlined"
                startIcon={<CancelIcon />}
                onClick={handleEditCancel}
                disabled={isSubmitting}
              >
                {t('common.cancel')}
              </Button>
            </Box>
          </Box>
        ) : (
          comment.contains_spoiler ? (
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
                  sx={{
                    color: "warning.main",
                    display: 'block',
                    mt: 0.5,
                    fontStyle: 'italic'
                  }}>
                  {t('comments.spoiler')}
                </Typography>
              )}
            </Box>
          ) : (
            <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              {comment.message}
            </Typography>
          )
        )}
        
        {!isEditing && (
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Tooltip title={t('novelSources.upvote')}>
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
              
              <Tooltip title={t('novelSources.downvote')}>
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

            {onAddReply ? (
              <Button 
                variant="outlined"
                size="small" 
                startIcon={<ReplyIcon />} 
                onClick={() => setIsReplying(!isReplying)}
                color="primary"
                sx={{ borderRadius: 2 }}
              >
                {isReplying ? t('comments.cancelReply') : t('comments.reply')}
              </Button>
            ) : (
              <Typography variant="caption" sx={{
                color: "text.secondary"
              }}>
                {t('comments.repliesDisabled')}
              </Typography>
            )}
          </Box>
        )}
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
          {t('comments.showReplies', { count: comment.replies!.length })}
        </Button>
      )}
    </Box>
  );
};

export default CommentItem;
