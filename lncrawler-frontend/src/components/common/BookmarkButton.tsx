import React, { useState } from 'react';
import { Box, IconButton } from '@mui/material';
import BookmarkIcon from '@mui/icons-material/Bookmark';
import BookmarkBorderIcon from '@mui/icons-material/BookmarkBorder';
import { userService } from '@services/user.service';
import { useAuth } from '@context/AuthContext';

interface BookmarkButtonProps {
  isBookmarked: boolean;
  slug: string;
  customSx?: React.CSSProperties | Record<string, any>;
}

const BookmarkButton: React.FC<BookmarkButtonProps> = ({ 
  isBookmarked: initialIsBookmarked,
  slug,
  customSx = {}
}) => {
  const { isAuthenticated } = useAuth();
  const [isBookmarked, setIsBookmarked] = useState<boolean>(initialIsBookmarked);
  const [bookmarkLoading, setBookmarkLoading] = useState(false);

  const handleBookmarkClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    
    if (!isAuthenticated || bookmarkLoading) return;
    
    try {
      setBookmarkLoading(true);
      
      if (isBookmarked) {
        await userService.removeNovelBookmark(slug);
        setIsBookmarked(false);
      } else {
        await userService.addNovelBookmark(slug);
        setIsBookmarked(true);
      }
    } catch (error) {
      console.error('Error toggling bookmark:', error);
    } finally {
      setBookmarkLoading(false);
    }
  };

  if (!isAuthenticated) return null;

  return (
    <Box sx={customSx}>
      <IconButton
        size="small"
        onClick={handleBookmarkClick}
        sx={{
          bgcolor: 'rgba(0, 0, 0, 0.6)',
          color: 'white',
          '&:hover': {
            bgcolor: 'rgba(0, 0, 0, 0.8)',
          },
          width: 36,
          height: 36,
        }}
      >
        {isBookmarked ? <BookmarkIcon /> : <BookmarkBorderIcon />}
      </IconButton>
    </Box>
  );
};

export default BookmarkButton;
