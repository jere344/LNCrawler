import React, { useState } from 'react';
import { getNovelDisplayTitle } from '@utils/Misc';
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
import type { SxProps } from '@mui/material';
import DoneAllIcon from '@mui/icons-material/DoneAll';
import { userService } from '@services/user.service';
import { useAuth } from '@context/AuthContext';
import { Novel } from '@models/novels_types';
import { useTranslation } from 'react-i18next';

/** True when the novel has chapters the user has not read yet. */
export const hasUnreadChapters = (novel: Novel): boolean => {
  if (novel.reading_history) {
    const latestChapterId = novel.reading_history.source_latest_chapter?.chapter_id || 0;
    const lastReadChapterId = novel.reading_history.last_read_chapter?.chapter_id;
    if (lastReadChapterId === undefined) return false;
    return latestChapterId > lastReadChapterId;
  }
  return Boolean(novel.is_bookmarked && novel.prefered_source?.latest_available_chapter);
};

/** Source slug and chapter number to mark as read, or null if none can be resolved. */
export const getMarkAsReadTarget = (
  novel: Novel
): { sourceSlug: string; chapterNumber: number } | null => {
  let sourceSlug: string;
  let chapterNumber: number;
  if (novel.reading_history) {
    sourceSlug = novel.reading_history.source_slug || novel.prefered_source?.source_slug || '';
    chapterNumber = novel.reading_history.source_latest_chapter?.chapter_id ||
                    novel.reading_history.last_read_chapter?.chapter_id || 0;
  } else {
    sourceSlug = novel.prefered_source?.source_slug || '';
    chapterNumber = novel.prefered_source?.latest_available_chapter?.chapter_id || 0;
  }
  return sourceSlug && chapterNumber > 0 ? { sourceSlug, chapterNumber } : null;
};

interface MarkAsReadButtonProps {
  novel: Novel;
  onMarkAsRead?: () => void;
  customSx?: SxProps;
}

const MarkAsReadButton: React.FC<MarkAsReadButtonProps> = ({
  novel,
  onMarkAsRead,
  customSx = {}
}) => {
  const { isAuthenticated } = useAuth();
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);

  const handleMarkAsReadClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();

    if (!isAuthenticated || isLoading || !hasUnreadChapters(novel)) return;

    setShowConfirmation(true);
  };

  const handleConfirmMarkAsRead = async () => {
    try {
      setIsLoading(true);
      setShowConfirmation(false);

      const target = getMarkAsReadTarget(novel);
      if (target) {
        await userService.markChapterAsRead(novel.slug, target.sourceSlug, target.chapterNumber);
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

  if (!isAuthenticated || !hasUnreadChapters(novel)) return null;

  return (
    <>
      <Box sx={customSx}>
        <Tooltip title={t('markAsRead.tooltip')} arrow>
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
        <DialogTitle>{t('markAsRead.confirmTitle')}</DialogTitle>
        <DialogContent>
          <Typography>
            {t('markAsRead.confirmBody', { title: getNovelDisplayTitle(novel) })}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancelConfirmation} color="inherit">
            {t('common.cancel')}
          </Button>
          <Button 
            onClick={handleConfirmMarkAsRead} 
            color="primary" 
            variant="contained"
            disabled={isLoading}
          >
            {t('markAsRead.confirm')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default MarkAsReadButton;
