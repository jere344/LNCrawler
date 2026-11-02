import React from 'react';
import { Box, Divider, Button, Tooltip, useMediaQuery, useTheme } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import DoneIcon from '@mui/icons-material/Done';
import CommentIcon from '@mui/icons-material/Comment';
import CircularProgress from '@mui/material/CircularProgress';
import { useTranslation } from 'react-i18next';
import DirectionalIcon from '../DirectionalIcon';

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
}) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  // Every button in the row shares this size: full width and medium on phones
  const buttonProps = { fullWidth: isMobile, size: isMobile ? 'medium' : 'large' } as const;

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
              startIcon={<DirectionalIcon><ArrowBackIcon /></DirectionalIcon>}
              onClick={onPrevious}
              variant="outlined"
              {...buttonProps}
            >
              {t('readerControls.previousChapter')}
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
              {...buttonProps}
            >
              {markReadSuccess ? t('readerControls.markedAsRead') : t('readerControls.markAsRead')}
            </Button>
          )}

          {onGoToComments && (
            <Tooltip title={t('readerControls.viewComments')}>
              <Button
                variant="outlined"
                color="primary"
                startIcon={<CommentIcon />}
                onClick={onGoToComments}
                {...buttonProps}
              >
                {t('readerControls.comments')}
              </Button>
            </Tooltip>
          )}
        </Box>

        {/* Right side - Next button */}
        <Box sx={{ width: isMobile ? '100%' : 'auto' }}>
          {nextChapter && (
            <Button
              endIcon={<DirectionalIcon><ArrowForwardIcon /></DirectionalIcon>}
              onClick={onNext}
              variant="contained"
              {...buttonProps}
            >
              {t('readerControls.nextChapter')}
            </Button>
          )}
        </Box>
      </Box>
    </>
  );
};

export default ReaderControls;
