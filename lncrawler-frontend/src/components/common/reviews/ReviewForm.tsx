import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  TextField,
  Rating,
  Button,
  Alert,
  CircularProgress,
} from '@mui/material';
import EditableMDXEditor from './EditableMDXEditor';
import { reviewService } from '@services/api';
import { CreateReviewData } from '@services/review.service';
import { useTranslation } from 'react-i18next';

interface ReviewFormProps {
  novelSlug: string;
  onReviewAdded: (review: any) => void;
  onCancel?: () => void;
  editingReview?: any;
}

const ReviewForm: React.FC<ReviewFormProps> = ({ 
  novelSlug, 
  onReviewAdded, 
  onCancel,
  editingReview 
}) => {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [rating, setRating] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editorKey, setEditorKey] = useState(0);
  const { t } = useTranslation();

  // Pre-populate form when editing
  useEffect(() => {
    if (editingReview) {
      setTitle(editingReview.title);
      setContent(editingReview.content);
      setRating(editingReview.rating);
      // Force editor to re-render with new content
      setEditorKey(prev => prev + 1);
    } else {
      // Reset form when not editing
      setTitle('');
      setContent('');
      setRating(null);
      setEditorKey(prev => prev + 1);
    }
  }, [editingReview]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !content.trim() || !rating) {
      setError(t('reviewForm.fillAll'));
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const reviewData: CreateReviewData = {
        title: title.trim(),
        content: content.trim(),
        rating: rating,
      };

      let updatedReview;
      if (editingReview) {
        // Update existing review
        updatedReview = await reviewService.updateReview(editingReview.id, reviewData);
      } else {
        // Create new review
        updatedReview = await reviewService.addReview(novelSlug, reviewData);
      }
      
      onReviewAdded(updatedReview);
      
      // Reset form
      setTitle('');
      setContent('');
      setRating(null);
    } catch (err: any) {
      console.error('Error saving review:', err);
      if (err.response?.data?.error) {
        setError(err.response.data.error);
      } else {
        setError(t(editingReview ? 'reviewForm.failedUpdate' : 'reviewForm.failedAdd'));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Paper 
      elevation={2} 
      sx={{ 
        p: 3, 
        mb: 3,
        borderRadius: 2,
        border: '1px solid',
        borderColor: 'divider'
      }}
    >
      <Typography variant="h6" gutterBottom>
        {t(editingReview ? 'reviewForm.headingEdit' : 'reviewForm.headingWrite')}
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Box component="form" onSubmit={handleSubmit}>
        <TextField
          fullWidth
          label={t('reviewForm.title')}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          margin="normal"
          required
          disabled={loading}
          placeholder={t('reviewForm.titlePlaceholder')}
        />

        <Box sx={{ mt: 2, mb: 2 }}>
          <Typography component="legend" gutterBottom>
            {t('reviewForm.ratingLegend')}
          </Typography>
          <Rating
            name="novel-rating"
            value={rating}
            onChange={(_, newValue) => setRating(newValue)}
            size="large"
            disabled={loading}
          />
        </Box>

        <Box sx={{ mt: 2, mb: 2 }}>
          <Typography component="legend" gutterBottom>
            {t('reviewForm.contentLegend')}
          </Typography>
          <EditableMDXEditor
            content={content}
            onChange={setContent}
            placeholder={t('reviewForm.contentPlaceholder')}
            editorKey={editorKey}
          />
        </Box>

        <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
          {onCancel && (
            <Button 
              variant="outlined" 
              onClick={onCancel}
              disabled={loading}
            >
              {t('common.cancel')}
            </Button>
          )}
          <Button
            type="submit"
            variant="contained"
            disabled={loading || !title.trim() || !content.trim() || !rating}
            startIcon={loading && <CircularProgress size={20} />}
          >
            {loading ? t(editingReview ? 'reviewForm.updating' : 'reviewForm.submitting') : t(editingReview ? 'reviewForm.updateReview' : 'reviewForm.submitReview')}
          </Button>
        </Box>
      </Box>
    </Paper>
  );
};

export default ReviewForm;
