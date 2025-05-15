import React from 'react';
import { Box, Card, Typography, Badge, ButtonBase } from '@mui/material';
import StarIcon from '@mui/icons-material/Star';
import BookIcon from '@mui/icons-material/Book';
import EmojiEventsIcon from '@mui/icons-material/EmojiEvents';
import { Novel } from '@models/novels_types';

interface NovelItemCardProps {
  novel: Novel;
  onClick: () => void;
  rank?: number;
}

const NovelItemCard: React.FC<NovelItemCardProps> = ({ novel, rank, onClick }) => {
  const coverUrl = novel.prefered_source?.cover_url || '';

  return (
    <ButtonBase 
      onClick={onClick}
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        height: '100%',
        width: '100%',
        textAlign: 'left',
        transition: 'transform 0.2s',
        '&:hover': {
          transform: 'translateY(-5px)',
        }
      }}
    >
      <Card 
        sx={{ 
          aspectRatio: '2/3',
          borderRadius: 1.5,
          overflow: 'hidden',
          boxShadow: 2,
          position: 'relative',
          mb: 1,
          mx: 'auto'
        }}
      >
        <Box
          component="img"
          src={coverUrl}
          alt={novel.title}
          sx={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
          }}
          
        />
        <Badge 
          sx={{
            position: 'absolute',
            bottom: 4,
            left: 4,
            background: 'rgba(0,0,0,0.7)',
            color: 'white',
            borderRadius: '3px',
            padding: '0 4px',
            display: 'flex',
            alignItems: 'center',
            gap: 0.3,
          }}
        >
          <StarIcon sx={{ fontSize: 14 }} />
          <Typography variant="caption">
            {novel.avg_rating ? novel.avg_rating.toFixed(1) : '-'}
          </Typography>
        </Badge>
      </Card>
      
      <Box sx={{ px: 0.5, width: '100%' }}>
        <Typography 
          variant="body2"
          component="h4" 
          sx={{
            fontWeight: 'bold',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            lineHeight: '1.2em',
            height: '2.4em',
            mb: 0.5
          }}
        >
          {novel.title}
        </Typography>
        
        <Box sx={{ 
          display: 'flex', 
          flexDirection: 'column', 
          gap: 0.25,
          mt: 0.5,
          fontSize: '0.75rem',
          color: 'text.secondary',
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <EmojiEventsIcon sx={{ fontSize: 14, flexShrink: 0 }} />
            <Typography 
              variant="caption" 
              component="span"
              noWrap
              sx={{ 
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              Rank {rank || '-'}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <BookIcon sx={{ fontSize: 14, flexShrink: 0 }} />
            <Typography 
              variant="caption" 
              component="span"
              noWrap
              sx={{ 
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {novel.total_chapters || novel.prefered_source?.chapters_count || 0} Chapters
            </Typography>
          </Box>
        </Box>
      </Box>
    </ButtonBase>
  );
};

export default NovelItemCard;
