import React from 'react';
import { Box, Divider, Button, useMediaQuery, useTheme } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import { useTranslation } from 'react-i18next';
import DirectionalIcon from '../DirectionalIcon';

interface ReaderControlsProps {
  prevChapter?: number | null;
  nextChapter?: number | null;
  onPrevious: () => void;
  onNext: () => void;
}

/**
 * Reader controls component that provides navigation and action buttons
 * for the chapter reader (bottom navigation and actions)
 */
const ReaderControls: React.FC<ReaderControlsProps> = ({
  prevChapter,
  nextChapter,
  onPrevious,
  onNext,
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
