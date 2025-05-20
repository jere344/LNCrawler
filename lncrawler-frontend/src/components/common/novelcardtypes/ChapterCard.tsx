import React from 'react';
import { Box, Card, Typography, ButtonBase, Skeleton } from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import { NovelFromSource } from '@models/novels_types';
import { formatTimeAgo, getChapterName, toLocalDate } from '@utils/Misc';
import defaultCover from '@assets/default-cover.jpg';

interface ChapterCardProps {
  source: NovelFromSource;
  onClick: () => void;
  isLoading?: boolean;
}

const ChapterCard: React.FC<ChapterCardProps> = ({ source, onClick, isLoading = false }) => {
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

  const chapterName = getChapterName(source.latest_available_chapter?.title || "");
  
  return (
    <ButtonBase 
      onClick={onClick} 
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
      }}>
        <Box
          component="img"
          src={source.cover_url || defaultCover}
          alt={source.title}
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
            Chapter {source.latest_available_chapter?.chapter_id}
            {chapterName ? ` : ${chapterName}` : ''}
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
            {source.last_chapter_update ? formatTimeAgo(toLocalDate(source.last_chapter_update)) : 'Unknown'}
          </Typography>
        </Box>
      </Box>
    </ButtonBase>
  );
};

export default ChapterCard;
