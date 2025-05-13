import React from 'react';
import { 
  Card, CardActionArea, CardMedia, CardContent, 
  Typography, Box, Badge, Chip
} from '@mui/material';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import WhatshotIcon from '@mui/icons-material/Whatshot';
import defaultCover from '@assets/default-cover.jpg';
import { Novel } from '@models/novels_types';
import { formatCount } from './BaseNovelCard';

interface TrendingNovelCardProps {
  novel: Novel;
  onClick?: () => void;
  isLoading?: boolean;
  rank?: number;
}

const TrendingNovelCard: React.FC<TrendingNovelCardProps> = ({ 
  novel, 
  onClick, 
  rank 
}) => {
  const preferredSource = novel.prefered_source;

  // Calculate trend percentage if both total and weekly views are available
  const trendPercentage = novel.total_views && novel.weekly_views 
    ? Math.round((novel.weekly_views / novel.total_views) * 100)
    : null;
  
  return (
    <Card 
      sx={{ 
        height: '100%', 
        display: 'flex', 
        flexDirection: 'column',
        position: 'relative',
        overflow: 'visible',
        transition: 'transform 0.3s ease, box-shadow 0.3s ease',
        '&:hover': {
          transform: 'translateY(-5px) scale(1.02)',
          boxShadow: '0px 10px 20px -5px rgba(0,0,0,0.2)',
        }
      }}
    >
      {rank !== undefined && (
        <Box 
          sx={{
            position: 'absolute',
            top: -10,
            left: -10,
            backgroundColor: 'primary.main',
            color: 'white',
            borderRadius: '50%',
            width: 36,
            height: 36,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 'bold',
            boxShadow: 2,
            zIndex: 1
          }}
        >
          {rank}
        </Box>
      )}
      
      <CardActionArea 
        sx={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'stretch' }}
        onClick={onClick}
      >
        <Badge
          badgeContent={
            <Box sx={{ 
              bgcolor: 'error.main', 
              color: 'white', 
              px: 1, 
              py: 0.5, 
              borderRadius: 1,
              display: 'flex',
              alignItems: 'center',
              gap: 0.5
            }}>
              <WhatshotIcon fontSize="small" />
              <Typography variant="caption" fontWeight="bold">
                HOT
              </Typography>
            </Box>
          }
          sx={{
            '& .MuiBadge-badge': {
              top: 16,
              right: 16,
              border: '2px solid',
              borderColor: 'background.paper',
            }
          }}
        >
          <CardMedia
            component="img"
            height="240"
            image={preferredSource?.cover_url || defaultCover}
            alt={novel.title}
            sx={{ 
              objectFit: 'cover',
            }}
          />
        </Badge>
        
        <CardContent sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
          <Typography 
            gutterBottom 
            variant="h6" 
            component="div" 
            sx={{ 
              fontWeight: 'bold',
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
          
          {/* Trending statistics */}
          <Box sx={{ mt: 'auto' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
              <TrendingUpIcon color="error" />
              <Typography 
                variant="body1" 
                color="error.main" 
                fontWeight="bold" 
                sx={{ ml: 1 }}
              >
                {formatCount(novel.weekly_views || 0)} views this week
              </Typography>
            </Box>
            
            {trendPercentage !== null && trendPercentage > 5 && (
              <Chip 
                label={`${trendPercentage}% of all views are from this week!`}
                color="error"
                size="small"
                sx={{ fontWeight: 'bold' }}
              />
            )}
            
            {preferredSource?.genres && preferredSource.genres.length > 0 && (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 1 }}>
                {preferredSource.genres.slice(0, 2).map((genre, index) => (
                  <Chip 
                    key={index}
                    label={genre}
                    size="small"
                    color="secondary"
                  />
                ))}
              </Box>
            )}
          </Box>
        </CardContent>
      </CardActionArea>
    </Card>
  );
};

export default TrendingNovelCard;
