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
  onPageModeChange: (enabled: boolean) => void;
  onShowPagesChange: (show: boolean) => void;
}

/**
 * Component for page mode settings
 */
const PageSettings: React.FC<PageSettingsProps> = ({
  pageMode,
  showPages,
  onPageModeChange,
  onShowPagesChange,
}) => {
  const handlePageModeChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onPageModeChange(event.target.checked);
  };

  const handleShowPagesChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onShowPagesChange(event.target.checked);
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
    </>
  );
};

export default PageSettings;
