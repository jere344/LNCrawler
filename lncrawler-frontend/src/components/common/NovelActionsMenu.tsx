import React, { useState } from 'react';
import { Box, IconButton, ListItemIcon, ListItemText, Menu, MenuItem } from '@mui/material';
import type { SxProps } from '@mui/material';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import BookmarkIcon from '@mui/icons-material/Bookmark';
import BookmarkBorderIcon from '@mui/icons-material/BookmarkBorder';
import PlaylistAddIcon from '@mui/icons-material/PlaylistAdd';
import { userService } from '@services/user.service';
import { useAuth } from '@context/AuthContext';
import { useTranslation } from 'react-i18next';
import AddToListDialog from '@components/readinglist/AddToListDialog';

interface NovelActionsMenuProps {
  novelId: string;
  novelTitle: string;
  slug: string;
  isBookmarked?: boolean | null;
  customSx?: SxProps;
  buttonSize?: number;
  variant?: 'cover' | 'body';
}

/**
 * Burger menu exposing bookmark and add-to-reading-list actions on novel cards
 * that don't render those actions directly. Only visible to logged-in users.
 */
const NovelActionsMenu: React.FC<NovelActionsMenuProps> = ({
  novelId,
  novelTitle,
  slug,
  isBookmarked = false,
  customSx = {},
  buttonSize = 36,
  variant = 'body',
}) => {
  const { isAuthenticated } = useAuth();
  const { t } = useTranslation();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [bookmarked, setBookmarked] = useState<boolean>(!!isBookmarked);
  const [bookmarkLoading, setBookmarkLoading] = useState(false);
  const [listOpen, setListOpen] = useState(false);

  if (!isAuthenticated) return null;

  const closeMenu = () => setAnchorEl(null);

  const handleToggleBookmark = async () => {
    closeMenu();
    if (bookmarkLoading) return;
    try {
      setBookmarkLoading(true);
      if (bookmarked) {
        await userService.removeNovelBookmark(slug);
        setBookmarked(false);
      } else {
        await userService.addNovelBookmark(slug);
        setBookmarked(true);
      }
    } catch (error) {
      console.error('Error toggling bookmark:', error);
    } finally {
      setBookmarkLoading(false);
    }
  };

  const handleAddToList = () => {
    closeMenu();
    setListOpen(true);
  };

  return (
    <>
      <Box sx={customSx}>
        <IconButton
          size="small"
          aria-label={t('novelActions.menu')}
          onClick={(e) => {
            e.stopPropagation();
            e.preventDefault();
            setAnchorEl(e.currentTarget);
          }}
          sx={{
            color: variant === 'cover' ? 'white' : 'primary.main',
            bgcolor: variant === 'cover' ? 'rgba(0, 0, 0, 0.6)' : 'transparent',
            '&:hover': {
              bgcolor: variant === 'cover' ? 'rgba(0, 0, 0, 0.8)' : 'transparent',
              color: variant === 'cover' ? 'white' : 'primary.light',
            },
            width: buttonSize,
            height: buttonSize,
          }}
        >
          <MoreVertIcon fontSize="small" />
        </IconButton>
      </Box>

      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={closeMenu}
      >
        <MenuItem onClick={handleToggleBookmark} disabled={bookmarkLoading}>
          <ListItemIcon>
            {bookmarked ? <BookmarkIcon fontSize="small" /> : <BookmarkBorderIcon fontSize="small" />}
          </ListItemIcon>
          <ListItemText>{bookmarked ? t('novelActions.removeBookmark') : t('novelActions.bookmark')}</ListItemText>
        </MenuItem>
        <MenuItem onClick={handleAddToList}>
          <ListItemIcon><PlaylistAddIcon fontSize="small" /></ListItemIcon>
          <ListItemText>{t('novelActions.addToReadingList')}</ListItemText>
        </MenuItem>
      </Menu>

      <AddToListDialog
        open={listOpen}
        onClose={() => setListOpen(false)}
        novelId={novelId}
        novelTitle={novelTitle}
      />
    </>
  );
};

export default NovelActionsMenu;
