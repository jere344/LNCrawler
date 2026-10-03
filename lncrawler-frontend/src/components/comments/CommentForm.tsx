import { useState, useEffect } from 'react';
import {
  Box,
  TextField,
  Button,
  FormControlLabel,
  Checkbox,
  Typography,
  Paper,
  Alert,
} from '@mui/material';
import { useAuth } from '../../context/AuthContext';
import { useTranslation } from 'react-i18next';

interface CommentFormProps {
  onSubmit: (commentData: { 
    author_name: string; 
    message: string; 
    contains_spoiler: boolean;
    parent_id?: string;
  }) => Promise<void>;
  isReply?: boolean;
  parentAuthor?: string;
  onCancel?: () => void;
}

const CommentForm = ({ 
  onSubmit, 
  isReply = false, 
  parentAuthor, 
  onCancel 
}: CommentFormProps) => {
  const { isAuthenticated, user } = useAuth(); // Get auth status and user
  const { t } = useTranslation();
  const [authorName, setAuthorName] = useState('');
  const [message, setMessage] = useState('');
  const [containsSpoiler, setContainsSpoiler] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (isAuthenticated && user) {
      setAuthorName(user.username);
    } else {
      // If user logs out while form is open, clear the name
      // Or if they were never logged in, ensure it's empty for them to fill
      setAuthorName(''); 
    }
  }, [isAuthenticated, user]);


  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!authorName.trim() && !isAuthenticated) { // Only require if not authenticated
      setError(t('comments.enterName'));
      return;
    }
    
    if (!message.trim()) {
      setError(t('comments.enterComment'));
      return;
    }
    
    setError(null);
    setIsSubmitting(true);
    
    try {
      await onSubmit({
        author_name: isAuthenticated && user ? user.username : authorName, // Send username if auth, else field value
        message,
        contains_spoiler: containsSpoiler
      });
      
      // Reset form on success
      if (!isAuthenticated) { // Don't clear author name if logged in
        setAuthorName('');
      }
      setMessage('');
      setContainsSpoiler(false);
      setSuccess(true);
      
      // Hide success message after 3 seconds
      setTimeout(() => {
        setSuccess(false);
        if (isReply && onCancel) {
          onCancel(); // Close reply form if this is a reply
        }
      }, 3000);
      
    } catch (err) {
      console.error('Error submitting comment:', err);
      setError(t('comments.submitFailed'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Paper 
      elevation={isReply ? 0 : 1} 
      sx={{ 
        p: 2, 
        mb: 2,
        bgcolor: isReply ? 'background.default' : 'background.paper',
        border: isReply ? '1px solid #e0e0e0' : 'none',
        borderRadius: 1
      }}
    >
      <Typography variant="h6" gutterBottom>
        {isReply ? t('comments.replyTo', { author: parentAuthor }) : t('comments.addComment')}
      </Typography>
      
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      
      {success && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(false)}>
          {isReply ? t('comments.replyPosted') : t('comments.commentPosted')}
        </Alert>
      )}
      
      <Box component="form" onSubmit={handleSubmit} noValidate>
        <TextField
          fullWidth
          label={t('comments.yourName')}
          margin="normal"
          value={authorName}
          onChange={(e) => setAuthorName(e.target.value)}
          required={!isAuthenticated} // Not required if authenticated
          disabled={isAuthenticated} // Disable if authenticated
        />
        
        <TextField
          fullWidth
          label={isReply ? t('comments.yourReply') : t('comments.yourComment')}
          multiline
          rows={isReply ? 3 : 4}
          margin="normal"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          required
        />
        
        <FormControlLabel
          control={
            <Checkbox 
              checked={containsSpoiler}
              onChange={(e) => setContainsSpoiler(e.target.checked)}
              color="primary"
            />
          }
          label={t('comments.containsSpoilers')}
          sx={{ mt: 1 }}
        />
        
        <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
          <Button
            type="submit"
            variant="contained"
            color="primary"
            disabled={isSubmitting}
          >
            {isSubmitting ? t('comments.posting') : isReply ? t('comments.postReply') : t('comments.postComment')}
          </Button>
          
          {isReply && onCancel && (
            <Button
              variant="outlined"
              onClick={onCancel}
              disabled={isSubmitting}
            >
              {t('common.cancel')}
            </Button>
          )}
        </Box>
      </Box>
    </Paper>
  );
};

export default CommentForm;
