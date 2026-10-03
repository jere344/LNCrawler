import React from 'react';
import { Box, Button, Typography, Grid as Grid } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import HomeIcon from '@mui/icons-material/Home';
import { Link as RouterLink } from 'react-router-dom'; // Import RouterLink
import { useTranslation } from 'react-i18next';

interface ReaderNavigationProps {
  prevChapter?: number | null;
  nextChapter?: number | null;
  onPrevious: () => void;
  onNext: () => void;
  onHome: () => void;
  variant?: 'buttons' | 'compact';
  showLabels?: boolean;
  // Add URL props
  prevUrl?: string;
  nextUrl?: string;
  homeUrl?: string;
}

/**
 * Navigation component for the chapter reader
 * Provides controls for navigating between chapters
 */
const ReaderNavigation: React.FC<ReaderNavigationProps> = ({
  prevChapter,
  nextChapter,
  onPrevious,
  onNext,
  onHome,
  variant = 'buttons',
  showLabels = true,
  prevUrl,
  nextUrl,
  homeUrl,
}) => {
  const { t } = useTranslation();

  if (variant === 'compact') {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
        {prevChapter ? (
          <Button 
            startIcon={<ArrowBackIcon />} 
            onClick={onPrevious}
            variant="outlined"
            component={prevUrl ? RouterLink : "a"}
            to={prevUrl}
          >
            {showLabels ? t('readerControls.previousChapter') : ''}
          </Button>
        ) : <></>}
        
        {nextChapter && (
          <Button 
            endIcon={<ArrowForwardIcon />} 
            onClick={onNext}
            variant="contained"
            component={nextUrl ? RouterLink : "a"}
            to={nextUrl}
          >
            {showLabels ? t('readerControls.nextChapter') : ''}
          </Button>
        )}
      </Box>
    );
  }

  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'medium' }}>{t('readerControls.chapterNavigation')}</Typography>
      <Grid container spacing={1}>
        <Grid size={4}>
          <Button 
            fullWidth 
            variant={prevChapter ? "contained" : "outlined"}
            color={prevChapter ? "primary" : "inherit"}
            startIcon={<ArrowBackIcon />}
            onClick={onPrevious}
            disabled={!prevChapter}
            size="medium"
            component={prevUrl ? RouterLink : "a"}
            to={prevUrl}
          >
            {t('readerControls.prev')}
          </Button>
        </Grid>
        <Grid size={4}>
          <Button 
            fullWidth 
            variant="outlined"
            startIcon={<HomeIcon />}
            onClick={onHome}
            size="medium"
            component={homeUrl ? RouterLink : "a"}
            to={homeUrl}
          >
            {t('readerControls.home')}
          </Button>
        </Grid>
        <Grid size={4}>
          <Button 
            fullWidth 
            variant={nextChapter ? "contained" : "outlined"}
            color={nextChapter ? "primary" : "inherit"}
            endIcon={<ArrowForwardIcon />}
            onClick={onNext}
            disabled={!nextChapter}
            size="medium"
            component={nextUrl ? RouterLink : "a"}
            to={nextUrl}
          >
            {t('readerControls.next')}
          </Button>
        </Grid>
      </Grid>
    </Box>
  );
};

export default ReaderNavigation;
