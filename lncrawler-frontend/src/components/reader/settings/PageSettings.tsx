import React from 'react';
import {
  Box,
  Typography,
  FormControlLabel,
  Switch,
} from '@mui/material';
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation();

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
          label={t('pageSettings.enablePageMode')}
        />
        <Typography variant="body2" color="textSecondary" sx={{ mt: 0.5 }}>
          {t('pageSettings.enablePageModeHint')}
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
          label={t('pageSettings.showPageNumbers')}
        />
        <Typography variant="body2" color="textSecondary" sx={{ mt: 0.5 }}>
          {t('pageSettings.showPageNumbersHint')}
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
          label={t('pageSettings.showPageSlider')}
        />
        <Typography variant="body2" color="textSecondary" sx={{ mt: 0.5 }}>
          {t('pageSettings.showPageSliderHint')}
        </Typography>
      </Box>
    </>
  );
};

export default PageSettings;
