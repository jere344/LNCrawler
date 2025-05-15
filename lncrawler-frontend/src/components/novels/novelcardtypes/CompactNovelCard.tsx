import React from 'react';
import { 
  Box, Card, Typography, Rating, ButtonBase
} from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import CommentIcon from '@mui/icons-material/Comment';
import defaultCover from '@assets/default-cover.jpg';
import { Novel } from '@models/novels_types';

interface CompactNovelCardProps {
  novel: Novel;
  onClick?: () => void;
  isLoading?: boolean;
  showClicks?: boolean;
  showTrends?: boolean;
  showRating?: boolean;
}

const CompactNovelCard: React.FC<CompactNovelCardProps> = ({ 
  novel, 
  onClick, 
  showClicks = false,
  showTrends = false,
  showRating = false
}) => {
  const formatter = Intl.NumberFormat('en', { notation: 'compact' });
  const coverUrl = novel.prefered_source?.cover_url || defaultCover;

  // Fixed dimensions for 2:3 ratio
  const coverHeight = 90; 
  const coverWidth = coverHeight * 2/3;

  return (
    <ButtonBase 
      onClick={onClick}
      sx={{
        display: 'flex', 
        justifyContent: 'flex-start', 
        alignItems: 'flex-start', 
        height: coverHeight + 'px',
        width: '100%',
        textAlign: 'left',
      }}
    >
      <Card
        sx={{
          width: coverWidth,
          minWidth: coverWidth,
          height: '100%',
          borderRadius: 1.5,
          overflow: 'hidden',
          boxShadow: 2,
          flexShrink: 0,
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
      </Card>
      
      <Box sx={{ 
        flexGrow: 1,
        flexShrink: 1,
        overflow: 'hidden',
        p: 1.5,
        display: 'flex', 
        flexDirection: 'column', 
        justifyContent: 'space-between',
        height: '100%'
      }}>
        <Typography 
          variant="body2"
          component="h4" 
          sx={{
            fontWeight: 'bold',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            display: '-webkit-box',
            WebkitLineClamp: 1,
            WebkitBoxOrient: 'vertical',
            mb: 0.5
          }}
        >
          {novel.title}
        </Typography>
        
        {showRating && (
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
            <Rating 
              value={novel.avg_rating || 0} 
              precision={0.1} 
              size="small" 
              readOnly 
            />
            <Typography variant="caption" component="span" sx={{ ml: 1, color: 'text.secondary' }}>
              ({novel.rating_count || 0})
            </Typography>
          </Box>
        )}
        
        <Box sx={{ 
          display: 'flex', 
          flexDirection: 'column', 
          gap: 0.25,
          fontSize: '0.75rem',
          color: 'text.secondary',
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <VisibilityIcon sx={{ fontSize: 14, flexShrink: 0 }} />
            <Typography 
              variant="caption" 
              component="span"
              noWrap
              sx={{ 
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {formatter.format(showTrends ? (novel.weekly_views || 0) : (novel.total_views || 0))}
              {showTrends ? ' (Weekly)' : ' (All times)'}
            </Typography>
          </Box>
          {(showClicks || showTrends) && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <CommentIcon sx={{ fontSize: 14, flexShrink: 0 }} />
              <Typography 
                variant="caption" 
                component="span"
                noWrap
                sx={{ 
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {formatter.format(0)} comments
              </Typography>
            </Box>
          )}
        </Box>
      </Box>
    </ButtonBase>
  );
};

export default CompactNovelCard;
