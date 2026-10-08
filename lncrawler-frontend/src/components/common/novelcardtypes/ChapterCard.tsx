import React from 'react';
import { Box, Card, Typography, ButtonBase, Skeleton } from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import { NovelFromSource } from '@models/novels_types';
import { formatTimeAgo, getChapterLabel } from '@utils/Misc';
import defaultCover from '@assets/default-cover.jpg';
import { Link } from 'react-router-dom';
import type { To } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAdultContent } from '@context/AdultContentContext';
import { AdultBadge } from '@components/common/AdultBadge';

interface ChapterCardProps {
  source: NovelFromSource;
  onClick?: () => void;
  isLoading?: boolean;
  to?: To;
  state?: unknown;
}

const ChapterCard: React.FC<ChapterCardProps> = ({ source, onClick, isLoading = false, to, state }) => {
  const { t } = useTranslation();
  const { isBlurred, revealHandler } = useAdultContent();
  const blurred = isBlurred(source.is_adult, source.novel_id);
  const coverHeight = 90;
  const coverWidth = coverHeight * 2/3;

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'flex-start', alignItems: 'flex-start', height: coverHeight + 'px', width: '100%' }}>
        <Skeleton variant="rectangular" sx={{ width: coverWidth, minWidth: coverWidth, height: '100%', borderRadius: 1.5, flexShrink: 0, boxShadow: 2 }} />
        <Box sx={{ flexGrow: 1, flexShrink: 1, overflow: 'hidden', p: 1.5, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', height: '100%' }}>
          <Box>
            <Skeleton variant="text" height={24} width="90%" sx={{ mb: 0.25 }} />
            <Skeleton variant="text" height={18} width="70%" sx={{ mb: 0.5 }} />
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 'auto' }}>
            <Skeleton variant="circular" width={14} height={14} />
            <Skeleton variant="text" width="60%" height={18} />
          </Box>
        </Box>
      </Box>
    );
  }

  return (
    <ButtonBase 
      onClick={onClick}
      component={to ? Link : 'button'}
      to={to}
      state={to ? state : undefined}
      sx={{ 
        display: 'flex', 
        justifyContent: 'flex-start', 
        height: coverHeight + 'px',
        width: '100%',
        textAlign: 'left',
        transition: 'transform 0.2s',
        '&:hover': {
          transform: 'translateY(-3px)',
        }
      }}
    >
      <Card sx={{ 
        width: coverWidth,
        minWidth: coverWidth,
        height: '100%', 
        flexShrink: 0, 
        borderRadius: 1.5,
        overflow: 'hidden',
        boxShadow: 2, 
        position: 'relative',
      }}>
        <Box
          component="img"
          src={source.cover_min_url || defaultCover}
          alt={source.title}
          onClick={blurred ? revealHandler(source.novel_id) : undefined}
          sx={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            cursor: blurred ? 'pointer' : undefined,
            filter: blurred ? 'blur(16px)' : 'none',
          }}
        />
        <AdultBadge isAdult={source.is_adult} novelId={source.novel_id} />
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
        <Box>
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
              mb: 0.25
            }}
          >
            {source.title}
          </Typography>
          
          <Typography 
            variant="caption"
            component="h5" 
            sx={{
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: '-webkit-box',
              WebkitLineClamp: 1,
              WebkitBoxOrient: 'vertical',
              color: 'text.secondary',
              mb: 0.5
            }}
          >
            {getChapterLabel(t, source.latest_available_chapter?.title, source.latest_available_chapter?.chapter_id)}
          </Typography>
        </Box>
        
        <Box sx={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: 0.5,
          color: 'text.secondary'
        }}>
          <EditIcon sx={{ fontSize: 14, flexShrink: 0 }} />
          <Typography 
            variant="caption"
            noWrap
            sx={{ 
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {source.last_chapter_update ? formatTimeAgo(new Date(source.last_chapter_update), t) : t('common.unknown')}
          </Typography>
        </Box>
      </Box>
    </ButtonBase>
  );
};

export default ChapterCard;
