import React from 'react';
import { 
  Box, Card, Typography, Rating, ButtonBase, Skeleton // Added Skeleton
} from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import CommentIcon from '@mui/icons-material/Comment';
import { Novel } from '@models/novels_types';
import { Link } from 'react-router-dom';
import type { To } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import NovelActionsMenu from '@components/common/NovelActionsMenu';
import { NovelCover } from '@components/common/NovelCover';
import CoverRowSkeleton from '@components/common/CoverRowSkeleton';
import { compactNumberFormatter, getNovelDisplayTitle, novelCoverUrl } from '@utils/Misc';

interface CompactNovelCardProps {
  novel: Novel;
  isLoading?: boolean;
  showClicks?: boolean;
  showTrends?: boolean;
  showRating?: boolean;
  to?: To;
  state?: unknown;
}

// Fixed dimensions for 2:3 ratio
const coverHeight = 90;
const coverWidth = coverHeight * 2/3;

const CompactNovelCard: React.FC<CompactNovelCardProps> = ({
  novel,
  isLoading = false,
  showClicks = false,
  showTrends = false,
  showRating = false,
  to,
  state
}) => {
  const { t, i18n } = useTranslation();

  if (isLoading) {
    return (
      <CoverRowSkeleton coverHeight={coverHeight}>
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
      </CoverRowSkeleton>
    );
  }

  const formatter = compactNumberFormatter(i18n.language);

  return (
    <Box sx={{ position: 'relative', width: '100%' }}>
    <NovelActionsMenu
      novelId={novel.id}
      displayTitle={getNovelDisplayTitle(novel)}
      slug={novel.slug}
      isBookmarked={novel.is_bookmarked}
      customSx={{ position: 'absolute', top: 4, right: 4, zIndex: 2 }}
      buttonSize={26}
    />
    <ButtonBase
      component={to ? Link : 'button'}
      to={to}
      state={to ? state : undefined}
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
        <NovelCover
          src={novelCoverUrl(novel.reading_source ?? novel.suggested_source)}
          alt={getNovelDisplayTitle(novel)}
          novelId={novel.id}
          isAdult={novel.is_adult}
          hasAudiobook={novel.has_audiobook}
          sx={{ width: '100%', height: '100%' }}
        />
      </Card>
      
      <Box sx={{ 
        flexGrow: 1,
        flexShrink: 1,
        overflow: 'hidden',
        p: 1.5,
        pr: 4,
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
          {getNovelDisplayTitle(novel)}
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
              {showTrends ? ` ${t('cards.weekly')}` : ` ${t('cards.allTimes')}`}
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
                {t('units.comments', { count: novel.comment_count })}
              </Typography>
            </Box>
          )}
        </Box>
      </Box>
    </ButtonBase>
    </Box>
  );
};

export default CompactNovelCard;
