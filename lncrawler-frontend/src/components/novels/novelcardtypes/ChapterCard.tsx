import React from 'react';
import { Box, Card, Typography, ButtonBase } from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import { NovelFromSource } from '@models/novels_types';
import { formatTimeAgo, getChapterName } from '@utils/Misc';

interface ChapterCardProps {
  source: NovelFromSource;
  onClick: () => void;
}

const ChapterCard: React.FC<ChapterCardProps> = ({ source, onClick }) => {
  const coverUrl = source.cover_url || '';

  const chapterName = (source.title && source.chapters_count !== 0) ? getChapterName(source.title) : '';
  
  const coverHeight = 90;
  const coverWidth = coverHeight * 2/3;

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
          src={coverUrl}
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
            Chapter {source.chapters_count}
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
            {source.last_chapter_update ? formatTimeAgo(source.last_chapter_update) : 'Unknown'}
          </Typography>
        </Box>
      </Box>
    </ButtonBase>
  );
};

export default ChapterCard;
