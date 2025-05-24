import React from 'react';
import { 
  Box, Card, Typography, Rating, ButtonBase, Skeleton // Added Skeleton
} from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import CommentIcon from '@mui/icons-material/Comment';
import defaultCover from '@assets/default-cover.jpg';
import { Novel } from '@models/novels_types';
import { Link } from 'react-router-dom';

interface CompactNovelCardProps {
  novel: Novel;
  onClick?: () => void;
  isLoading?: boolean;
  showClicks?: boolean;
  showTrends?: boolean;
  showRating?: boolean;
  to?: string;
}

const CompactNovelCard: React.FC<CompactNovelCardProps> = ({ 
  novel, 
  onClick, 
  isLoading = false,
  showClicks = false,
  showTrends = false,
  showRating = false,
  to
}) => {
  const coverHeight = 90; 
  const coverWidth = coverHeight * 2/3;

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'flex-start', alignItems: 'flex-start', height: coverHeight + 'px', width: '100%' }}>
        <Skeleton variant="rectangular" sx={{ width: coverWidth, minWidth: coverWidth, height: '100%', borderRadius: 1.5, flexShrink: 0, boxShadow: 2 }} />
        <Box sx={{ flexGrow: 1, flexShrink: 1, overflow: 'hidden', p: 1.5, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', height: '100%' }}>
          <Skeleton variant="text" height={24} width="80%" sx={{ mb: 0.5 }} />
          {showRating && (
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
              <Skeleton variant="rectangular" width={80} height={16} /> {/* Rating stars */}
              <Skeleton variant="text" width={30} height={16} sx={{ ml: 1 }} /> {/* Rating count */}
            </Box>
          )}
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.25, mt: 'auto' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Skeleton variant="circular" width={14} height={14} />
              <Skeleton variant="text" width="70%" height={18} />
            </Box>
            {(showClicks || showTrends) && ( // Assuming one of these implies a second line of stats
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Skeleton variant="circular" width={14} height={14} />
                <Skeleton variant="text" width="60%" height={18} />
              </Box>
            )}
          </Box>
        </Box>
      </Box>
    );
  }

  const formatter = Intl.NumberFormat('en', { notation: 'compact' });

  // Fixed dimensions for 2:3 ratio
  const coverHeightFixed = 90; 
  const coverWidthFixed = coverHeightFixed * 2/3;

  return (
    <ButtonBase 
      onClick={onClick}
      component={to ? Link : 'button'}
      to={to}
      sx={{
        display: 'flex', 
        justifyContent: 'flex-start', 
        alignItems: 'flex-start', 
        height: coverHeightFixed + 'px',
        width: '100%',
        textAlign: 'left',
      }}
    >
      <Card
        sx={{
          width: coverWidthFixed,
          minWidth: coverWidthFixed,
          height: '100%',
          borderRadius: 1.5,
          overflow: 'hidden',
          boxShadow: 2,
          flexShrink: 0,
        }}
      >
        <Box
          component="img"
          src={novel.prefered_source?.cover_url || defaultCover}
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
            mb: 0.5,
            lineHeight: 1,
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
                {formatter.format(novel.comment_count)} comments
              </Typography>
            </Box>
          )}
        </Box>
      </Box>
    </ButtonBase>
  );
};

export default CompactNovelCard;
