import React from 'react';
import { 
  AppBar, 
  Toolbar, 
  IconButton, 
  Typography, 
  Box, 
  Tooltip, 
  Slide 
} from '@mui/material';
import ListIcon from '@mui/icons-material/List';
import HomeIcon from '@mui/icons-material/Home';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import BookmarkAddIcon from '@mui/icons-material/BookmarkAdd';
import DoneIcon from '@mui/icons-material/Done';
import SettingsIcon from '@mui/icons-material/Settings';
import CloseIcon from '@mui/icons-material/Close';
import { useTheme } from '@mui/material/styles';

interface ReaderToolbarProps {
  isMobile: boolean;
  controlsVisible: boolean;
  title: string;
  prevChapter?: number | null;
  nextChapter?: number | null;
  isAuthenticated: boolean;
  markReadSuccess: boolean;
  markingAsRead: boolean;
  onMarkAsRead: () => void;
  onChapterList: () => void;
  onHome: () => void;
  onPrevious: () => void;
  onNext: () => void;
  onSettings: () => void;
  onCloseControls: () => void;
}

/**
 * Toolbar component for the chapter reader
 * Provides different layouts for desktop and mobile
 */
const ReaderToolbar: React.FC<ReaderToolbarProps> = ({
  isMobile,
  controlsVisible,
  title,
  prevChapter,
  nextChapter,
  isAuthenticated,
  markReadSuccess,
  markingAsRead,
  onMarkAsRead,
  onChapterList,
  onHome,
  onPrevious,
  onNext,
  onSettings,
  onCloseControls,
}) => {
  const theme = useTheme();

  // Desktop Toolbar
  if (!isMobile) {
    return (
      <AppBar position="sticky" color="default" elevation={1} sx={{ top: 0 }}>
        <Toolbar>
          <IconButton edge="start" color="inherit" onClick={onChapterList}>
            <ListIcon />
          </IconButton>
          <IconButton color="inherit" onClick={onHome}>
            <HomeIcon />
          </IconButton>
          
          <Box sx={{ flexGrow: 1, display: 'flex', justifyContent: 'center' }}>
            {prevChapter && (
              <IconButton color="inherit" onClick={onPrevious}>
                <ArrowBackIcon />
              </IconButton>
            )}
            
            <Typography variant="h6" sx={{ flexGrow: 0, textAlign: 'center', fontSize: { sm: '1.25rem' }, mx: 2 }}>
              {title}
            </Typography>
            
            {nextChapter && (
              <IconButton color="inherit" onClick={onNext}>
                <ArrowForwardIcon />
              </IconButton>
            )}
          </Box>
          
          {isAuthenticated && (
            <Tooltip title="Mark as read">
              <IconButton 
                color="primary" 
                onClick={onMarkAsRead} 
                disabled={markingAsRead || markReadSuccess}
                sx={{ mr: 1 }}
              >
                {markReadSuccess ? <DoneIcon /> : <BookmarkAddIcon />}
              </IconButton>
            </Tooltip>
          )}
          
          <IconButton color="inherit" onClick={onSettings}>
            <SettingsIcon />
          </IconButton>
        </Toolbar>
      </AppBar>
    );
  }

  return (
    <Slide direction="down" in={controlsVisible} mountOnEnter unmountOnExit>
      <AppBar 
        position="fixed" 
        color="default" 
        elevation={4} 
        sx={{ 
          top: 0,
          zIndex: theme.zIndex.drawer + 1,
          backgroundColor: theme.palette.background.paper,
          borderBottom: `1px solid ${theme.palette.divider}`,
          backdropFilter: 'blur(8px)',
          boxShadow: 3
        }}
      >
        <Toolbar sx={{ justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <IconButton edge="start" color="inherit" onClick={onChapterList} sx={{ mr: 1 }}>
              <ListIcon />
            </IconButton>
            <IconButton color="inherit" onClick={onHome}>
              <HomeIcon />
            </IconButton>
          </Box>
          
          <Typography 
            variant="subtitle1" 
            noWrap 
            sx={{ 
              fontWeight: 'medium',
              maxWidth: 'calc(100% - 160px)',
              textAlign: 'center'
            }}
          >
            {title}
          </Typography>
          
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            {isAuthenticated && (
              <IconButton 
                color="primary" 
                onClick={onMarkAsRead} 
                disabled={markingAsRead || markReadSuccess}
              >
                {markReadSuccess ? <DoneIcon /> : <BookmarkAddIcon />}
              </IconButton>
            )}
            <IconButton color="inherit" onClick={onCloseControls}>
              <CloseIcon />
            </IconButton>
          </Box>
        </Toolbar>
      </AppBar>
    </Slide>
  );
};

export default ReaderToolbar;
