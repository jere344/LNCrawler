import React from 'react';
import { Box, Button, Typography, Grid2 as Grid } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import HomeIcon from '@mui/icons-material/Home';

interface ReaderNavigationProps {
  prevChapter?: number | null;
  nextChapter?: number | null;
  onPrevious: () => void;
  onNext: () => void;
  onHome: () => void;
  variant?: 'buttons' | 'compact';
  showLabels?: boolean;
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
}) => {
  if (variant === 'compact') {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
        {prevChapter ? (
          <Button 
            startIcon={<ArrowBackIcon />} 
            onClick={onPrevious}
            variant="outlined"
            component="a"
          >
            {showLabels ? 'Previous Chapter' : ''}
          </Button>
        ) : <div></div>}
        
        {nextChapter && (
          <Button 
            endIcon={<ArrowForwardIcon />} 
            onClick={onNext}
            variant="contained"
          >
            {showLabels ? 'Next Chapter' : ''}
          </Button>
        )}
      </Box>
    );
  }

  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'medium' }}>Chapter Navigation</Typography>
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
          >
            Prev
          </Button>
        </Grid>
        <Grid size={4}>
          <Button 
            fullWidth 
            variant="outlined"
            startIcon={<HomeIcon />}
            onClick={onHome}
            size="medium"
          >
            Home
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
          >
            Next
          </Button>
        </Grid>
      </Grid>
    </Box>
  );
};

export default ReaderNavigation;
