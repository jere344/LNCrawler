import React from 'react';
import { 
  Card, CardActionArea, CardMedia, CardContent, 
  Typography, Box, Rating, Chip, Skeleton
} from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import defaultCover from '@assets/default-cover.jpg';
import { Novel } from '@models/novels_types';

export interface BaseNovelCardProps {
  novel: Novel;
  onClick?: () => void;
  isLoading?: boolean;
}

export function formatCount(count: number): string {
  if (count >= 1000000) {
    return `${(count / 1000000).toFixed(1)}M`;
  } else if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}K`;
  }
  return `${count}`;
}

export const BaseNovelCard: React.FC<BaseNovelCardProps> = ({ 
  novel, 
  onClick, 
  isLoading = false 
}) => {
  const preferredSource = novel.prefered_source;
  
  if (isLoading) {
    return (
      <Card sx={{ 
        height: '100%', 
        display: 'flex', 
        flexDirection: 'column'
      }}>
        <Box sx={{ paddingTop: '150%', position: 'relative' }}>
          <Skeleton 
            variant="rectangular" 
            sx={{ 
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%'
            }} 
          />
        </Box>
        <CardContent>
          <Skeleton variant="text" height={40} />
          <Skeleton variant="text" width="60%" />
          <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
            <Skeleton variant="rectangular" width={80} height={24} />
            <Skeleton variant="rectangular" width={80} height={24} />
          </Box>
        </CardContent>
      </Card>
    );
  }

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
        <Box sx={{ position: 'relative', paddingTop: '150%' /* 2:3 aspect ratio */ }}>
          <CardMedia
            component="img"
            image={preferredSource?.cover_url || defaultCover}
            alt={novel.title}
            sx={{ 
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              objectFit: 'cover'
            }}
          />
        </Box>
        <CardContent sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', pt: 1.5 }}>
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
                {novel.rating_count > 0 && ` (${formatCount(novel.rating_count)})`}
              </Typography>
            </Box>
          )}
          
          {/* Basic stats */}
          <Box sx={{ mt: 'auto', display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            {novel.total_views !== undefined && (
              <Chip 
                icon={<VisibilityIcon fontSize="small" />}
                label={`${formatCount(novel.total_views)} views`}
                size="small"
                variant="outlined"
              />
            )}
            
            {novel.total_chapters > 0 && (
              <Chip 
                icon={<MenuBookIcon fontSize="small" />}
                label={`${novel.total_chapters} chapters`}
                size="small"
                variant="outlined"
              />
            )}
          </Box>
        </CardContent>
      </CardActionArea>
    </Card>
  );
};

export default BaseNovelCard;
