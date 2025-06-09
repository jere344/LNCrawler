import React from 'react';
import {
  Box,
  Typography,
  FormControlLabel,
  Switch,
} from '@mui/material';

interface PageSettingsProps {
  pageMode: boolean;
  showPages: boolean;
  showPageSlider: boolean;
  onPageModeChange: (enabled: boolean) => void;
  onShowPagesChange: (show: boolean) => void;
  onShowPageSliderChange: (show: boolean) => void;
}

/**
 * Component for page mode settings
 */
const PageSettings: React.FC<PageSettingsProps> = ({
  pageMode,
  showPages,
  showPageSlider,
  onPageModeChange,
  onShowPagesChange,
  onShowPageSliderChange,
}) => {
  const handlePageModeChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onPageModeChange(event.target.checked);
  };

  const handleShowPagesChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onShowPagesChange(event.target.checked);
  };

  const handleShowPageSliderChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onShowPageSliderChange(event.target.checked);
  };

  return (
    <>
      <Box sx={{ mb: 2 }}>
        <FormControlLabel
          control={
            <Switch
              checked={pageMode}
              onChange={handlePageModeChange}
              color="primary"
            />
          }
          label="Enable Page Mode"
        />
        <Typography variant="body2" color="textSecondary" sx={{ mt: 0.5 }}>
          Switch from scroll-based to page-based reading
        </Typography>
      </Box>

      <Box sx={{ mb: 2 }}>
        <FormControlLabel
          control={
            <Switch
              checked={showPages}
              onChange={handleShowPagesChange}
              color="primary"
              disabled={!pageMode}
            />
          }
          label="Show Page Numbers"
        />
        <Typography variant="body2" color="textSecondary" sx={{ mt: 0.5 }}>
          Display current page and total pages
        </Typography>
      </Box>

      <Box sx={{ mb: 2 }}>
        <FormControlLabel
          control={
            <Switch
              checked={showPageSlider}
              onChange={handleShowPageSliderChange}
              color="primary"
              disabled={!pageMode || !showPages}
            />
          }
          label="Show Page Slider"
        />
        <Typography variant="body2" color="textSecondary" sx={{ mt: 0.5 }}>
          Display slider for quickly navigating between pages
        </Typography>
      </Box>
    </>
  );
};

export default PageSettings;
