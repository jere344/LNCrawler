import React from 'react';
import { 
  Card, CardActionArea, CardMedia, CardContent, 
  Typography, Box, Badge, Chip, Skeleton // Added Skeleton
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
  rank,
  isLoading = false 
}) => {
  if (isLoading) {
    return (
      <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'visible' }}>
        {rank !== undefined && (
          <Skeleton variant="circular" width={30} height={30} sx={{ position: 'absolute', top: -8, left: -8, zIndex: 1 }} />
        )}
        <Box sx={{ position: 'relative', width: '100%', aspectRatio: '2/3' }}>
          <Skeleton variant="rectangular" sx={{ width: '100%', height: '100%' }} />
          {/* Placeholder for "HOT" badge */}
          <Skeleton variant="rectangular" width={50} height={24} sx={{ position: 'absolute', top: 10, right: 10, borderRadius: 1, transform: 'translate(50%, -50%)' }}/>
        </Box>
        <CardContent sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', pt: 1, pb: 1, px: 1.5, '&:last-child': { pb: 1 } }}>
          <Skeleton variant="text" height={28} sx={{ mb: 0.5 }} />
          <Box sx={{ display: 'flex', alignItems: 'center', mt: 'auto' }}>
            <Skeleton variant="circular" width={16} height={16} sx={{ mr: 0.5 }} />
            <Skeleton variant="text" width="60%" height={20} />
          </Box>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
            <Skeleton variant="rectangular" width={60} height={20} sx={{ borderRadius: '16px' }} />
          </Box>
        </CardContent>
      </Card>
    );
  }

  const preferredSource = novel.prefered_source;
  
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
          transform: 'translateY(-3px) scale(1.01)',
          boxShadow: '0px 6px 12px -3px rgba(0,0,0,0.2)',
        }
      }}
    >
      {rank !== undefined && (
        <Box 
          sx={{
            position: 'absolute',
            top: -8,
            left: -8,
            backgroundColor: 'primary.main',
            color: 'white',
            borderRadius: '50%',
            width: 30,
            height: 30,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 'bold',
            boxShadow: 2,
            zIndex: 1,
            fontSize: '0.9rem'
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
              px: 0.7, 
              py: 0.3, 
              borderRadius: 1,
              display: 'flex',
              alignItems: 'center',
              gap: 0.3
            }}>
              <WhatshotIcon sx={{ fontSize: '0.9rem' }} />
              <Typography variant="caption" fontWeight="bold" fontSize="0.7rem">
                HOT
              </Typography>
            </Box>
          }
          sx={{
            '& .MuiBadge-badge': {
              top: 12,
              right: 12,
              border: '2px solid',
              borderColor: 'background.paper',
            },
            display: 'block',
            width: '100%'
          }}
        >
          <CardMedia
            component="img"
            image={preferredSource?.cover_url || defaultCover}
            alt={novel.title}
            sx={{ 
              width: '100%',
              aspectRatio: '2/3',
              objectFit: 'cover',
              display: 'block',
            }}
          />
        </Badge>
        
        <CardContent sx={{ 
          flexGrow: 1, 
          display: 'flex', 
          flexDirection: 'column', 
          pt: 1, 
          pb: 1, 
          px: 1.5,
          '&:last-child': { pb: 1 }
        }}>
          <Typography 
            variant="subtitle1" 
            component="div" 
            sx={{ 
              fontWeight: 'bold',
              lineHeight: 1.2,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              mb: 0.5
            }}
          >
            {novel.title}
          </Typography>
          
          {/* Trending statistics - simplified */}
          <Box sx={{ display: 'flex', alignItems: 'center', mt: 'auto' }}>
            <TrendingUpIcon color="error" sx={{ fontSize: '1rem' }} />
            <Typography 
              variant="body2" 
              color="error.main" 
              fontWeight="bold" 
              sx={{ ml: 0.5, fontSize: '0.85rem' }}
            >
              {formatCount(novel.weekly_views || 0)} views
            </Typography>
          </Box>
          
          {preferredSource?.genres && preferredSource.genres.length > 0 && (
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
              {preferredSource.genres.slice(0, 1).map((genre, index) => (
                <Chip 
                  key={index}
                  label={genre}
                  size="small"
                  color="secondary"
                  sx={{ height: 20, '& .MuiChip-label': { px: 1, py: 0, fontSize: '0.7rem' } }}
                />
              ))}
            </Box>
          )}
        </CardContent>
      </CardActionArea>
    </Card>
  );
};

export default TrendingNovelCard;
