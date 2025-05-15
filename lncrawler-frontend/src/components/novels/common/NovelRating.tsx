import { useState } from 'react';
import { Rating, Typography, Box, alpha, useTheme } from '@mui/material';
import StarIcon from '@mui/icons-material/Star';
import StarBorderIcon from '@mui/icons-material/StarBorder';
import { novelService } from '../../../services/api';

interface NovelRatingProps {
  novelSlug: string;
  initialUserRating: number | null;
  initialAvgRating: number | null;
  initialRatingCount: number;
  onRatingSuccess?: (avgRating: number, ratingCount: number, userRating: number) => void;
  disabled?: boolean;
  size?: 'small' | 'medium' | 'large';
}

const NovelRating: React.FC<NovelRatingProps> = ({
  novelSlug,
  initialUserRating,
  initialAvgRating,
  initialRatingCount,
  onRatingSuccess,
  disabled = false,
  size = 'small',
}) => {
  const theme = useTheme();
  const [userRating, setUserRating] = useState<number | null>(initialUserRating);
  const [avgRating, setAvgRating] = useState<number | null>(initialAvgRating);
  const [ratingCount, setRatingCount] = useState<number>(initialRatingCount);
  const [ratingInProgress, setRatingInProgress] = useState<boolean>(false);

  const handleRatingChange = async (_event: React.SyntheticEvent, value: number | null) => {
    if (!value || !novelSlug || ratingInProgress) return;

    setRatingInProgress(true);
    try {
      const ratingResponse = await novelService.rateNovel(novelSlug, value);
      setUserRating(ratingResponse.user_rating);
      setAvgRating(ratingResponse.avg_rating);
      setRatingCount(ratingResponse.rating_count);
      if (onRatingSuccess) {
        onRatingSuccess(ratingResponse.avg_rating, ratingResponse.rating_count, ratingResponse.user_rating);
      }
    } catch (err) {
      console.error('Error rating novel:', err);
      // Optionally, revert to previous state or show an error message
    } finally {
      setRatingInProgress(false);
    }
  };

  return (
    <Box 
      sx={{ 
        display: 'inline-flex', 
        alignItems: 'center',
        bgcolor: alpha('#f39c12', 0.3),
        backdropFilter: 'blur(10px)',
        px: 2, 
        py: 0.75, 
        borderRadius: 6,
        border: `1px solid ${alpha('#f39c12', 0.5)}`,
      }}
    >
      <Rating
        name={`novel-rating-${novelSlug}`}
        value={userRating || 0}
        onChange={handleRatingChange}
        precision={1}
        icon={<StarIcon fontSize={size} sx={{ color: '#f39c12' }} />}
        emptyIcon={<StarBorderIcon fontSize={size} sx={{ color: alpha('#f39c12', 0.6) }} />}
        disabled={disabled || ratingInProgress}
        size={size}
      />
      
      <Typography 
        variant="body2" 
        sx={{ ml: 1, color: theme.palette.common.white, fontWeight: 600 }}
      >
        {avgRating ? `${avgRating.toFixed(1)}` : 'No ratings'}
        {ratingCount > 0 ? 
          <Box component="span" sx={{ ml: 0.5, color: alpha(theme.palette.common.white, 0.7) }}>
            ({ratingCount} {ratingCount === 1 ? 'rating' : 'ratings'})
          </Box> : ''}
      </Typography>
    </Box>
  );
};

export default NovelRating;
