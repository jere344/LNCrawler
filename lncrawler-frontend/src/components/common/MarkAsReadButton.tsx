import React, { useState } from 'react';
import { Box, IconButton, Tooltip } from '@mui/material';
import type { SxProps } from '@mui/material';
import DoneAllIcon from '@mui/icons-material/DoneAll';
import { userService } from '@services/user.service';
import { useAuth } from '@context/AuthContext';
import { LibraryNovel } from '@models/novels_types';
import { useTranslation } from 'react-i18next';
import MarkAsReadConfirmDialog from './MarkAsReadConfirmDialog';

/** True when the novel has chapters the user has not read yet. */
export const hasUnreadChapters = (novel: LibraryNovel): boolean => {
  if (novel.reading_history) {
    const latestChapterId = novel.reading_history.source_latest_chapter?.chapter_id || 0;
    const lastReadChapterId = novel.reading_history.last_read_chapter?.chapter_id;
    if (lastReadChapterId === undefined) return false;
    return latestChapterId > lastReadChapterId;
  }
  return Boolean(novel.is_bookmarked && novel.prefered_source?.latest_available_chapter);
};

/** Unread chapter count shown on the cover, or null when there is none. */
export const getUnreadChapterCount = (novel: LibraryNovel): number | null => {
  if (novel.reading_history) {
    // Only chapters with content count (backend supplies the count), so
    // gaps left by failed downloads don't inflate the badge.
    const unread = novel.reading_history.unread_chapters;
    if (unread === undefined || unread === null) {
      return null;
    }
    return unread > 0 ? unread : null;
  }
  if (novel.is_bookmarked && novel.prefered_source) {
    const available = novel.prefered_source.available_chapters_count
      ?? novel.prefered_source.latest_available_chapter?.chapter_id;
    return available && available > 0 ? available : null;
  }
  return null;
};

/** Source slug and chapter number to mark as read, or null if none can be resolved. */
export const getMarkAsReadTarget = (
  novel: LibraryNovel
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
  novel: LibraryNovel;
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

      <MarkAsReadConfirmDialog
        open={showConfirmation}
        novel={novel}
        loading={isLoading}
        onConfirm={handleConfirmMarkAsRead}
        onClose={handleCancelConfirmation}
      />
    </>
  );
};

export default MarkAsReadButton;
