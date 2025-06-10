import React, { useState } from 'react';
import { 
  Box, 
  IconButton, 
  Tooltip, 
  Dialog, 
  DialogTitle, 
  DialogContent, 
  DialogActions, 
  Button, 
  Typography 
} from '@mui/material';
import DoneAllIcon from '@mui/icons-material/DoneAll';
import { userService } from '@services/user.service';
import { useAuth } from '@context/AuthContext';
import { Novel } from '@models/novels_types';

interface MarkAsReadButtonProps {
  novel: Novel;
  onMarkAsRead?: () => void;
  customSx?: React.CSSProperties | Record<string, any>;
}

const MarkAsReadButton: React.FC<MarkAsReadButtonProps> = ({ 
  novel,
  onMarkAsRead,
  customSx = {}
}) => {
  const { isAuthenticated } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);

  // Check if there are unread chapters
  const hasUnreadChapters = () => {
    if (novel.reading_history) {
      const latestChapterId = novel.reading_history.source_latest_chapter?.chapter_id || 0;
      const lastReadChapterId = novel.reading_history.last_read_chapter.chapter_id;
      return latestChapterId > lastReadChapterId;
    }
    return novel.is_bookmarked && novel.prefered_source?.latest_available_chapter;
  };

  const handleMarkAsReadClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    
    if (!isAuthenticated || isLoading || !hasUnreadChapters()) return;
    
    setShowConfirmation(true);
  };

  const handleConfirmMarkAsRead = async () => {
    try {
      setIsLoading(true);
      setShowConfirmation(false);
      
      const novelSlug = novel.slug;
      let sourceSlug: string;
      let chapterNumber: number;

      if (novel.reading_history) {
        sourceSlug = novel.reading_history.source_slug || novel.prefered_source?.source_slug || '';
        chapterNumber = novel.reading_history.source_latest_chapter?.chapter_id || 
                       novel.reading_history.last_read_chapter.chapter_id;
      } else {
        sourceSlug = novel.prefered_source?.source_slug || '';
        chapterNumber = novel.prefered_source?.latest_available_chapter?.chapter_id || 0;
      }

      if (sourceSlug && chapterNumber > 0) {
        await userService.markChapterAsRead(novelSlug, sourceSlug, chapterNumber);
        onMarkAsRead?.();
      }
    } catch (error) {
      console.error('Error marking novel as read:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCancelConfirmation = () => {
    setShowConfirmation(false);
  };

  if (!isAuthenticated || !hasUnreadChapters()) return null;

  return (
    <>
      <Box sx={customSx}>
        <Tooltip title="Mark as read" arrow>
          <IconButton
            size="small"
            onClick={handleMarkAsReadClick}
            disabled={isLoading}
            sx={{
              bgcolor: 'rgba(0, 0, 0, 0.6)',
              color: 'white',
              '&:hover': {
                bgcolor: 'rgba(0, 0, 0, 0.8)',
              },
              '&:disabled': {
                bgcolor: 'rgba(0, 0, 0, 0.4)',
                color: 'rgba(255, 255, 255, 0.5)',
              },
              width: 36,
              height: 36,
            }}
          >
            <DoneAllIcon />
          </IconButton>
        </Tooltip>
      </Box>

      <Dialog
        open={showConfirmation}
        onClose={handleCancelConfirmation}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Confirm Mark as Read</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to mark "{novel.title}" as read? This will mark all chapters up to the latest available chapter as read.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancelConfirmation} color="inherit">
            Cancel
          </Button>
          <Button 
            onClick={handleConfirmMarkAsRead} 
            color="primary" 
            variant="contained"
            disabled={isLoading}
          >
            Mark as Read
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default MarkAsReadButton;
