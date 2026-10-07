import { Box, Stepper, Step, StepLabel, Paper } from '@mui/material';
import { useTranslation } from 'react-i18next';

export type DownloadStep = 'search' | 'select' | 'download' | 'complete';

interface DownloadStepperProps {
  activeStep: DownloadStep;
}

const steps = [
  { key: 'search', labelKey: 'downloader.stepSearch' },
  { key: 'select', labelKey: 'downloader.stepSelectNovel' },
  { key: 'download', labelKey: 'downloader.stepDownload' },
  { key: 'complete', labelKey: 'downloader.stepComplete' }
];

const DownloadStepper = ({ activeStep }: DownloadStepperProps) => {
  const { t } = useTranslation();
  // Convert activeStep string to numeric index
  const currentStep = steps.findIndex((step) => step.key === activeStep);

  return (
    <Paper sx={{ p: 1, mb: 2 }} elevation={1}>
      <Box sx={{ width: '100%' }}>
        <Stepper activeStep={currentStep} alternativeLabel>
          {steps.map((step) => (
            <Step key={step.key}>
              <StepLabel>{t(step.labelKey)}</StepLabel>
            </Step>
          ))}
        </Stepper>
      </Box>
    </Paper>
  );
};

export default DownloadStepper;
