import React from 'react';
import { Box, Divider, Button, Tooltip, useMediaQuery, useTheme } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import DoneIcon from '@mui/icons-material/Done';
import CommentIcon from '@mui/icons-material/Comment';
import CircularProgress from '@mui/material/CircularProgress';
import { Link as RouterLink } from 'react-router-dom'; // Import RouterLink

interface ReaderControlsProps {
  prevChapter?: number | null;
  nextChapter?: number | null;
  isAuthenticated: boolean;
  markReadSuccess: boolean;
  markingAsRead: boolean;
  onMarkAsRead: () => void;
  onPrevious: () => void;
  onNext: () => void;
  onGoToComments?: () => void;
  variant?: 'full' | 'compact';
  // Add URL props
  prevUrl?: string;
  nextUrl?: string;
}

/**
 * Reader controls component that provides navigation and action buttons 
 * for the chapter reader (bottom navigation and actions)
 */
const ReaderControls: React.FC<ReaderControlsProps> = ({
  prevChapter,
  nextChapter,
  isAuthenticated,
  markReadSuccess,
  markingAsRead,
  onMarkAsRead,
  onPrevious,
  onNext,
  onGoToComments,
  variant = 'full',
  prevUrl,
  nextUrl,
}) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  if (variant === 'compact') {
    return (
      <Box sx={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        mt: 2,
        flexDirection: isMobile ? 'column' : 'row',
        gap: isMobile ? 2 : 0
      }}>
        {prevChapter ? (
          <Button 
            startIcon={<ArrowBackIcon />} 
            onClick={onPrevious}
            variant="outlined"
            component={prevUrl ? RouterLink : "a"}
            to={prevUrl}
            fullWidth={isMobile}
            size={isMobile ? "medium" : "large"}
          >
            Previous Chapter
          </Button>
        ) : <div></div>}
        
        {nextChapter && (
          <Button 
            endIcon={<ArrowForwardIcon />} 
            onClick={onNext}
            variant="contained"
            component={nextUrl ? RouterLink : "a"}
            to={nextUrl}
            fullWidth={isMobile}
            size={isMobile ? "medium" : "large"}
          >
            Next Chapter
          </Button>
        )}
      </Box>
    );
  }

  return (
    <>
      <Divider sx={{ mt: 4, mb: 2 }} />
      <Box sx={{ 
        display: 'flex', 
        flexDirection: isMobile ? 'column' : 'row',
        justifyContent: 'space-between', 
        alignItems: 'center',
        gap: 2,
        mt: 2,
        mb: 2
      }}>
        {/* Left side - Previous button */}
        <Box sx={{ width: isMobile ? '100%' : 'auto' }}>
          {prevChapter ? (
            <Button 
              startIcon={<ArrowBackIcon />} 
              onClick={onPrevious}
              variant="outlined"
              component={prevUrl ? RouterLink : "a"}
              to={prevUrl}
              fullWidth={isMobile}
              size={isMobile ? "medium" : "large"}
            >
              Previous Chapter
            </Button>
          ) : <div></div>}
        </Box>
        
        {/* Center - Mark as Read & Comments buttons */}
        <Box sx={{ 
          display: 'flex', 
          flexDirection: isMobile ? 'column' : 'row',
          width: isMobile ? '100%' : 'auto',
          gap: 2, 
          justifyContent: 'center' 
        }}>
          {isAuthenticated && (
            <Button
              variant="outlined"
              color={markReadSuccess ? "success" : "primary"}
              startIcon={markingAsRead ? <CircularProgress size={20} /> : <DoneIcon />}
              onClick={onMarkAsRead}
              disabled={markReadSuccess || markingAsRead}
              fullWidth={isMobile}
              size={isMobile ? "medium" : "large"}
            >
              {markReadSuccess ? "Marked as Read" : "Mark as Read"}
            </Button>
          )}
          
          {onGoToComments && (
            <Tooltip title="View chapter comments">
              <Button
                variant="outlined"
                color="primary"
                startIcon={<CommentIcon />}
                onClick={onGoToComments}
                fullWidth={isMobile}
                size={isMobile ? "medium" : "large"}
              >
                Comments
              </Button>
            </Tooltip>
          )}
        </Box>
        
        {/* Right side - Next button */}
        <Box sx={{ width: isMobile ? '100%' : 'auto' }}>
          {nextChapter && (
            <Button 
              endIcon={<ArrowForwardIcon />} 
              onClick={onNext}
              variant="contained"
              component={nextUrl ? RouterLink : "a"}
              to={nextUrl}
              fullWidth={isMobile}
              size={isMobile ? "medium" : "large"}
            >
              Next Chapter
            </Button>
          )}
        </Box>
      </Box>
    </>
  );
};

export default ReaderControls;
