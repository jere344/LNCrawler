import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Avatar,
  Rating,
  Button,
  Divider,
  Pagination,
  Alert,
  CircularProgress,
  IconButton,
  Menu,
  MenuItem,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from '@mui/material';
import { formatTimeAgo } from '@utils/Misc';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import { reviewService } from '@services/api';
import { Review, ReviewsResponse } from '@services/review.service';
import ReviewReactions from '../common/reviews/ReviewReactions';
import ReviewForm from '../common/reviews/ReviewForm';
import { useAuth } from '@context/AuthContext';
import ReadOnlyMDXEditor from '../common/reviews/ReadOnlyMDXEditor';

interface ReviewsProps {
  novelSlug: string;
  initialReviews?: Review[];
  showAddReview?: boolean;
}

const Reviews: React.FC<ReviewsProps> = ({ 
  novelSlug, 
  initialReviews,
  showAddReview = true 
}) => {
  const { user } = useAuth();
  const [reviews, setReviews] = useState<Review[]>(initialReviews || []);
  const [loading, setLoading] = useState(!initialReviews);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalReviews, setTotalReviews] = useState(0);
  const [showReviewForm, setShowReviewForm] = useState(false);
  const [editingReview, setEditingReview] = useState<Review | null>(null);
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const [selectedReview, setSelectedReview] = useState<Review | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  const loadReviews = async (page = 1) => {
    setLoading(true);
    setError(null);
    
    try {
      const response: ReviewsResponse = await reviewService.getNovelReviews(novelSlug, page);
      setReviews(response.reviews);
      setCurrentPage(response.pagination.current_page);
      setTotalPages(response.pagination.total_pages);
      setTotalReviews(response.pagination.total_reviews);
    } catch (err) {
      console.error('Error loading reviews:', err);
      setError('Failed to load reviews. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!initialReviews) {
      loadReviews();
    }
  }, [novelSlug, initialReviews]);

  const handleReviewAdded = (newReview: Review) => {
    if (editingReview) {
      // Update existing review in the list
      setReviews(reviews.map(r => r.id === editingReview.id ? newReview : r));
      setEditingReview(null);
    } else {
      // Add new review to the list
      setReviews([newReview, ...reviews]);
      setTotalReviews(totalReviews + 1);
    }
    setShowReviewForm(false);
  };

  const handlePageChange = (_: React.ChangeEvent<unknown>, page: number) => {
    loadReviews(page);
  };

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>, review: Review) => {
    setMenuAnchor(event.currentTarget);
    setSelectedReview(review);
  };

  const handleMenuClose = () => {
    setMenuAnchor(null);
    setSelectedReview(null);
  };

  const handleEditReview = () => {
    setEditingReview(selectedReview);
    setShowReviewForm(true);
    handleMenuClose();
  };

  const handleDeleteReview = async () => {
    if (!selectedReview) return;
    
    try {
      await reviewService.deleteReview(selectedReview.id);
      setReviews(reviews.filter(r => r.id !== selectedReview.id));
      setTotalReviews(totalReviews - 1);
      setDeleteDialogOpen(false);
      handleMenuClose();
    } catch (error) {
      console.error('Error deleting review:', error);
      setError('Failed to delete review. Please try again.');
    }
  };

  const renderReviewContent = (content: string) => {
    return <ReadOnlyMDXEditor content={content} uniqueKey={`review-content-${content.substring(0, 50)}`} />;
  };

  if (loading && !reviews.length) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* Add Review Section */}
      {showAddReview && user && !showReviewForm && (
        <Box sx={{ mb: 3 }}>
          <Button
            variant="contained"
            onClick={() => setShowReviewForm(true)}
            sx={{ borderRadius: 2 }}
          >
            Write a Review
          </Button>
        </Box>
      )}

      {/* Review Form */}
      {showReviewForm && user && (
        <ReviewForm
          novelSlug={novelSlug}
          onReviewAdded={handleReviewAdded}
          onCancel={() => {
            setShowReviewForm(false);
            setEditingReview(null);
          }}
          editingReview={editingReview}
        />
      )}

      {/* Reviews Header */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          Reviews ({totalReviews})
        </Typography>
      </Box>

      {/* Reviews List */}
      {reviews.length === 0 ? (
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="body1" color="text.secondary">
            No reviews yet. Be the first to review this novel!
          </Typography>
        </Paper>
      ) : (
        <Box>
          {reviews.map((review, index) => (
            <Paper 
              key={review.id} 
              elevation={1} 
              sx={{ 
                p: 3, 
                mb: 2,
                borderRadius: 2,
                border: '1px solid',
                borderColor: 'divider'
              }}
            >
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Avatar 
                    src={review.user.profile_pic} 
                    alt={review.user.username}
                    sx={{ width: 40, height: 40 }}
                  >
                    {review.user.username.charAt(0).toUpperCase()}
                  </Avatar>
                  <Box>
                    <Typography variant="subtitle1" fontWeight="bold">
                      {review.user.username}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {formatTimeAgo(new Date(review.created_at))}
                    </Typography>
                  </Box>
                </Box>
                
                {user && user.id === review.user.id && (
                  <IconButton
                    size="small"
                    onClick={(e) => handleMenuOpen(e, review)}
                  >
                    <MoreVertIcon />
                  </IconButton>
                )}
              </Box>

              <Typography variant="h6" gutterBottom>
                {review.title}
              </Typography>

              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Rating value={review.rating} readOnly size="small" />
                <Typography variant="body2" color="text.secondary" sx={{ ml: 1 }}>
                  {review.rating} stars
                </Typography>
              </Box>

              {renderReviewContent(review.content)}

              <ReviewReactions
                reviewId={review.id}
                reactions={review.reactions}
                currentUserReaction={review.current_user_reaction}
              />

              {index < reviews.length - 1 && <Divider sx={{ mt: 2 }} />}
            </Paper>
          ))}

          {/* Pagination */}
          {totalPages > 1 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
              <Pagination
                count={totalPages}
                page={currentPage}
                onChange={handlePageChange}
                color="primary"
                size="large"
              />
            </Box>
          )}
        </Box>
      )}

      {/* Review Actions Menu */}
      <Menu
        anchorEl={menuAnchor}
        open={Boolean(menuAnchor)}
        onClose={handleMenuClose}
      >
        <MenuItem onClick={handleEditReview}>
          <EditIcon sx={{ mr: 1 }} fontSize="small" />
          Edit Review
        </MenuItem>
        <MenuItem onClick={() => setDeleteDialogOpen(true)}>
          <DeleteIcon sx={{ mr: 1 }} fontSize="small" />
          Delete Review
        </MenuItem>
      </Menu>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>Delete Review</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete this review? This action cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleDeleteReview} color="error" variant="contained">
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Reviews;
