import React from 'react';
import { 
  Card, CardActionArea, CardMedia, CardContent, 
  Typography, Box, Rating, Chip
} from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import defaultCover from '@assets/default-cover.jpg';

interface NovelCardProps {
  novel: {
    id: string;
    title: string;
    slug: string;
    cover_url: string | null;
    avg_rating?: number | null;
    rating_count?: number;
    total_views?: number;
    weekly_views?: number;
  };
  onClick?: () => void;
}

const NovelCard: React.FC<NovelCardProps> = ({ novel, onClick }) => {
  
  return (
    <Card 
      sx={{ 
        height: '100%', 
        display: 'flex', 
        flexDirection: 'column',
        transition: 'transform 0.3s ease, box-shadow 0.3s ease',
        '&:hover': {
          transform: 'translateY(-5px)',
          boxShadow: '0px 10px 15px -3px rgba(0,0,0,0.1)',
        }
      }}
    >
      <CardActionArea 
        sx={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'stretch' }}
        onClick={onClick}
      >
        <CardMedia
          component="img"
          height="220"
          image={novel.cover_url ? (import.meta.env.VITE_API_BASE_URL + "/" + novel.cover_url) : defaultCover}
          alt={novel.title}
          sx={{ 
            objectFit: 'cover',
          }}
        />
        <CardContent sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
          <Typography 
            gutterBottom 
            variant="subtitle1" 
            component="div" 
            sx={{ 
              fontWeight: 'medium',
              lineHeight: 1.2,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              mb: 1
            }}
          >
            {novel.title}
          </Typography>
          
          {novel.avg_rating !== undefined && (
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
              <Rating 
                value={novel.avg_rating || 0} 
                precision={0.5} 
                readOnly 
                size="small" 
              />
              <Typography variant="body2" color="text.secondary" sx={{ ml: 0.5 }}>
                {novel.avg_rating ? novel.avg_rating.toFixed(1) : 'N/A'}
                {novel.rating_count && novel.rating_count > 0 && (
                  ` (${novel.rating_count})`
                )}
              </Typography>
            </Box>
          )}
          
          {/* View statistics */}
          <Box sx={{ mt: 'auto', display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            {novel.total_views !== undefined && (
              <Chip 
                icon={<VisibilityIcon fontSize="small" />}
                label={`${novel.total_views >= 1000 
                  ? `${(novel.total_views / 1000).toFixed(1)}K` 
                  : novel.total_views} views`}
                size="small"
                variant="outlined"
              />
            )}
            
            {novel.weekly_views !== undefined && novel.weekly_views > 0 && (
              <Chip 
                icon={<TrendingUpIcon fontSize="small" />}
                label={`${novel.weekly_views >= 1000 
                  ? `${(novel.weekly_views / 1000).toFixed(1)}K` 
                  : novel.weekly_views} this week`}
                size="small"
                color="primary"
                variant="outlined"
              />
            )}
          </Box>
        </CardContent>
      </CardActionArea>
    </Card>
  );
};

export default NovelCard;
