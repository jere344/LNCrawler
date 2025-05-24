import React from 'react';
import {
  Card,
  CardContent,
  CardActions,
  Typography,
  Button,
  IconButton,
  Tooltip,
  Box,
  Stack,
  Chip
} from '@mui/material';
import { Link } from 'react-router-dom';
import { Novel } from '@models/novels_types';
import CloseIcon from '@mui/icons-material/Close';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import InfoIcon from '@mui/icons-material/Info';
import { formatTimeAgo, getChapterName, toLocalDate } from '@utils/Misc';

interface ReadingHistoryCardProps {
  novel: Novel;
  onDelete: (novelId: string) => void;
}

const ReadingHistoryCard: React.FC<ReadingHistoryCardProps> = ({ novel, onDelete }) => {
  const continue_chapter = novel.reading_history?.next_chapter || novel.reading_history?.last_read_chapter;

  return (
    <Card 
      elevation={2} 
      sx={{ 
        display: 'flex', 
        position: 'relative', 
        overflow: 'visible',
        height: '100%',
        '&:hover': {
          boxShadow: 6
        }
      }}
    >
      {/* Delete button positioned absolutely in the top right */}
      <Tooltip title="Remove from history">
        <IconButton 
          size="medium" 
          onClick={() => onDelete(novel.id)}
          sx={{ 
            position: 'absolute', 
            top: 8, 
            right: 8, 
            zIndex: 2,
          }}
        >
          <CloseIcon fontSize="medium" />
        </IconButton>
      </Tooltip>

      {/* Cover image with 2:3 aspect ratio */}
      <Box 
        sx={{
          width: 120,
          minWidth: 120,
          height: '100%',
          backgroundImage: novel.prefered_source?.cover_url 
            ? `url(${novel.prefered_source.cover_url})` 
            : 'linear-gradient(to bottom right, #6a11cb, #2575fc)',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          borderTopLeftRadius: 4,
          borderBottomLeftRadius: 4,
        }}
        component={Link}
        to={`/novels/${novel.slug}`}
        className="clickable"
      />

      {/* Content area */}
      <Box sx={{ display: 'flex', flexDirection: 'column', flexGrow: 1, width: '100%' }}>
        <CardContent sx={{ pb: 1, flexGrow: 1 }}>
          <Typography 
            variant="h6" 
            component={Link}
            to={`/novels/${novel.slug}`}
            sx={{ 
              fontWeight: 'bold',
              cursor: 'pointer',
              '&:hover': { color: 'primary.main' },
              color: 'text.primary',
              textDecoration: 'none',
            }}
          >
            {novel.title}
          </Typography>
          
          {novel.reading_history && continue_chapter && (
            <Box sx={{ mt: 1 }}>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="body2" color="text.secondary">
                  Last read:
                </Typography>
                <Chip 
                  size="small" 
                  label={formatTimeAgo(toLocalDate(novel.reading_history.last_read_at))}
                  color="primary" 
                  variant="outlined"
                />
              </Stack>
              
              <Typography variant="body2" gutterBottom>
                <strong>Chapter:</strong> {novel.reading_history.last_read_chapter.chapter_id} 
                {getChapterName(novel.reading_history.last_read_chapter.title) != '' ? ' - ' : ''}
                {getChapterName(novel.reading_history.last_read_chapter.title)}
              </Typography>
              
              {novel.reading_history.last_read_chapter.volume_title && (
                <Typography variant="body2" gutterBottom>
                  <strong>Volume:</strong> {novel.reading_history.last_read_chapter.volume_title}
                </Typography>
              )}
              
              <Typography variant="caption" display="block" color="text.secondary" sx={{ mt: 1 }}>
                {toLocalDate(novel.reading_history.last_read_at).toLocaleString()}
              </Typography>
            </Box>
          )}
        </CardContent>
        
        <CardActions sx={{ pt: 0 }}>
          <Button 
            size="small" 
            color="primary" 
            variant="contained"
            startIcon={<MenuBookIcon />}
            disabled={!novel.reading_history}
            sx={{ mr: 1 }}
            component={Link}
            to={novel.reading_history && continue_chapter ? `/novels/${novel.reading_history.novel_slug}/${novel.reading_history.source_slug}/chapter/${continue_chapter.chapter_id}` : ''}
          >
            Continue
          </Button>
          <Button
            size="small"
            color="secondary"
            variant="outlined"
            startIcon={<InfoIcon />}
            component={Link}
            to={`/novels/${novel.slug}`}
          >
            Details
          </Button>
        </CardActions>
      </Box>
    </Card>
  );
};

export default ReadingHistoryCard;
