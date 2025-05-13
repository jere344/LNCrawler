import React from 'react';
import { 
  Card, CardActionArea, CardMedia, CardContent, 
  Typography, Box, Rating
} from '@mui/material';
import defaultCover from '@assets/default-cover.jpg';
import { Novel } from '@models/novels_types';

interface CompactNovelCardProps {
  novel: Novel;
  onClick?: () => void;
  isLoading?: boolean;
}

const CompactNovelCard: React.FC<CompactNovelCardProps> = ({ novel, onClick }) => {
  const preferredSource = novel.prefered_source;
  
  return (
    <Card 
      sx={{ 
        height: '100%', 
        display: 'flex',
        transition: 'transform 0.2s ease',
        '&:hover': {
          transform: 'translateY(-3px)',
        }
      }}
    >
      <CardActionArea 
        sx={{ display: 'flex', height: '100%', alignItems: 'stretch', justifyContent: 'flex-start' }}
        onClick={onClick}
      >
        <Box sx={{ width: 60, position: 'relative' }}>
          <CardMedia
            component="img"
            sx={{ 
              width: 60, 
              height: '90px', // 2:3 aspect ratio
              objectFit: 'cover' 
            }}
            image={preferredSource?.cover_url || defaultCover}
            alt={novel.title}
          />
        </Box>
        <CardContent sx={{ flex: '1', paddingY: 1 }}>
          <Typography 
            variant="subtitle2" 
            component="div" 
            sx={{ 
              fontWeight: 'medium',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: '-webkit-box',
              WebkitLineClamp: 1,
              WebkitBoxOrient: 'vertical',
            }}
          >
            {novel.title}
          </Typography>
          
          {novel.avg_rating !== undefined && (
            <Box sx={{ display: 'flex', alignItems: 'center', mt: 0.5 }}>
              <Rating 
                value={novel.avg_rating || 0} 
                precision={0.5} 
                readOnly 
                size="small" 
              />
              <Typography variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>
                {novel.avg_rating?.toFixed(1) || 'N/A'}
              </Typography>
            </Box>
          )}
          
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
            {novel.total_chapters} chapters
          </Typography>
        </CardContent>
      </CardActionArea>
    </Card>
  );
};

export default CompactNovelCard;
