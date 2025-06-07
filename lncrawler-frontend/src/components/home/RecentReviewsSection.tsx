import React, { useState } from 'react';
import { 
  Typography, 
  Box, 
  Divider, 
  Button, 
  Grid2 as Grid, 
  Avatar, 
  Rating, 
  Card, 
  CardContent,
  Link as MuiLink,
  useTheme
} from '@mui/material';
import { Link } from 'react-router-dom';
import { Review } from '@services/review.service';
import ReadOnlyMDXEditor from '@components/common/reviews/ReadOnlyMDXEditor';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { formatTimeAgo } from '@utils/Misc';

interface RecentReviewsSectionProps {
  reviews?: Review[];
  isLoading: boolean;
}

const RecentReviewsSection: React.FC<RecentReviewsSectionProps> = ({ reviews, isLoading }) => {
  const [expandedReviews, setExpandedReviews] = useState<Record<string, boolean>>({});
    const theme = useTheme();

  const handleExpandToggle = (reviewId: string) => {
    setExpandedReviews(prev => ({
      ...prev,
      [reviewId]: !prev[reviewId]
    }));
  };

  return (
    <Box sx={{ mb: 6 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5" component="h2" fontWeight="bold">
          Latest Reviews
        </Typography>
      </Box>
      <Divider sx={{ mb: 3 }} />
      
      {isLoading ? (
        <Grid container spacing={2}>
          {[...Array(4)].map((_, index) => (
            <Grid size={{ xs: 12, md: 6 }} key={`review-skeleton-${index}`}>
              <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                <CardContent sx={{ flex: '1 0 auto', p: 3 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <Box sx={{ bgcolor: 'grey.300', width: 40, height: 40, borderRadius: '50%' }} />
                    <Box sx={{ ml: 2 }}>
                      <Box sx={{ bgcolor: 'grey.300', width: 120, height: 20, mb: 1 }} />
                      <Box sx={{ bgcolor: 'grey.300', width: 80, height: 16 }} />
                    </Box>
                  </Box>
                  <Box sx={{ bgcolor: 'grey.300', width: '100%', height: 24, mb: 2 }} />
                  <Box sx={{ bgcolor: 'grey.300', width: 120, height: 24, mb: 3 }} />
                  <Box sx={{ bgcolor: 'grey.300', width: '100%', height: 100 }} />
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      ) : (
        <Grid container spacing={2}>
          {reviews?.map((review) => {
            const isExpanded = expandedReviews[review.id] || false;
            
            return (
              <Grid size={{ xs: 12, md: 6 }} key={review.id}>
                <Card sx={{ 
                  height: '100%', 
                  display: 'flex', 
                  flexDirection: 'column',
                  borderRadius: 2,
                  border: '1px solid',
                  borderColor: 'divider'
                }}>
                  <CardContent sx={{ flex: '1 0 auto', p: 3 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <Avatar 
                          src={review.user.profile_pic} 
                          alt={review.user.username}
                        >
                          {review.user.username.charAt(0).toUpperCase()}
                        </Avatar>
                        <Box sx={{ ml: 1 }}>
                          <Typography variant="body2" fontWeight="bold">
                            {review.user.username}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {formatTimeAgo(new Date(review.created_at))}
                          </Typography>
                        </Box>
                      </Box>
                      <Box>
                        <MuiLink component={Link} to={`/novels/${review.novel_slug}`}>
                          <Typography variant="body2" color="primary">
                            {review.novel_title}
                          </Typography>
                        </MuiLink>
                      </Box>
                    </Box>
                    
                    <Typography variant="subtitle1" fontWeight="bold" gutterBottom>
                      {review.title}
                    </Typography>
                    
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                      <Rating value={review.rating} readOnly size="small" />
                      <Typography variant="body2" color="text.secondary" sx={{ ml: 1 }}>
                        {review.rating} stars
                      </Typography>
                    </Box>
                    
                    <Box sx={{
                      maxHeight: isExpanded ? 'none' : 100,
                      overflow: isExpanded ? 'visible' : 'hidden',
                      position: 'relative',
                      mb: 1
                    }}>
                      <ReadOnlyMDXEditor 
                        content={review.content} 
                        uniqueKey={`home-review-${review.id}`} 
                      />
                      {!isExpanded && (
                        <Box sx={{ 
                          position: 'absolute', 
                          bottom: 0, 
                          left: 0, 
                          right: 0, 
                          height: '50px', 
                          background: `linear-gradient(to top, ${theme.palette.background.paper} 0%, transparent 100%)`,
                        }} />
                      )}
                    </Box>
                    
                    <Box sx={{ mt: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Button
                        onClick={() => handleExpandToggle(review.id)}
                        startIcon={isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                        variant="text"
                        size="small"
                      >
                        {isExpanded ? 'Show Less' : 'Show More'}
                      </Button>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            );
          })}
        </Grid>
      )}
    </Box>
  );
};

export default RecentReviewsSection;
