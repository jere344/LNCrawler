import React from 'react';
import { Box, Card, Typography, Badge, ButtonBase, Skeleton } from '@mui/material';
import StarIcon from '@mui/icons-material/Star';
import BookIcon from '@mui/icons-material/Book';
import EmojiEventsIcon from '@mui/icons-material/EmojiEvents';
import { Novel } from '@models/novels_types';
import defaultCover from '@assets/default-cover.jpg';
import { Link } from 'react-router-dom';
import type { To } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import NovelActionsMenu from '@components/common/NovelActionsMenu';
import { useAdultContent } from '@context/AdultContentContext';
import { AdultBadge } from '@components/common/AdultBadge';

interface NovelItemCardProps {
  novel: Novel;
  onClick?: () => void;
  rank?: number;
  isLoading?: boolean;
  to?: To;
  state?: unknown;
}

const NovelItemCard: React.FC<NovelItemCardProps> = ({ novel, rank, onClick, isLoading = false, to, state }) => {
  const { t } = useTranslation();
  const { isBlurred, revealHandler } = useAdultContent();
  const blurred = isBlurred(novel.is_adult, novel.id);
  const displaySource = novel.reading_source ?? novel.prefered_source;
  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', height: '100%', width: '100%' }}>
        <Card sx={{ aspectRatio: '2/3', borderRadius: 1.5, overflow: 'hidden', mb: 1, width: '100%', boxShadow: 2 }}>
          <Skeleton variant="rectangular" sx={{ width: '100%', height: '100%' }} />
        </Card>
        <Box sx={{ px: 0.5, width: '100%' }}>
          <Skeleton variant="text" height={20} sx={{ mb: 0.25 }} />
          <Skeleton variant="text" height={20} width="80%" sx={{ mb: 0.5 }} />
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.25, mt: 0.5 }}>
            <Skeleton variant="text" width="50%" height={15} />
            <Skeleton variant="text" width="70%" height={15} />
          </Box>
        </Box>
      </Box>
    );
  }

  return (
    <Box sx={{
      position: 'relative',
      height: '100%',
      width: '100%',
      transition: 'transform 0.2s',
      '&:hover': {
        transform: 'translateY(-5px)',
        zIndex: 2,
      }
    }}>
    <NovelActionsMenu
      novelId={novel.id}
      novelTitle={novel.title}
      slug={novel.slug}
      isBookmarked={novel.is_bookmarked}
      customSx={{ position: 'absolute', bottom: 8, right: 8, zIndex: 2 }}
      buttonSize={28}
    />
    <ButtonBase 
      onClick={onClick}
      component={to ? Link : 'button'}
      to={to}
      state={to ? state : undefined}
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        height: '100%',
        width: '100%',
        textAlign: 'left',
        position: 'relative',
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
          src={displaySource?.cover_min_url || defaultCover}
          alt={novel.title}
          onClick={blurred ? revealHandler(novel.id) : undefined}
          sx={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            cursor: blurred ? 'pointer' : undefined,
            filter: blurred ? 'blur(16px)' : 'none',
          }}
          
        />
        <AdultBadge isAdult={novel.is_adult} novelId={novel.id} />
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
              {t('cards.rank', { rank: rank || '-' })}
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
              {t('cards.chaptersCount', { count: displaySource?.chapters_count || 0 })}
            </Typography>
          </Box>
        </Box>
      </Box>
    </ButtonBase>
    </Box>
  );
};

export default NovelItemCard;
