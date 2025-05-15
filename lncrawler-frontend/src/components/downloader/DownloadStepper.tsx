import { Box, Stepper, Step, StepLabel, Paper } from '@mui/material';

export type DownloadStep = 'search' | 'select' | 'download' | 'complete';

interface DownloadStepperProps {
  activeStep: DownloadStep;
}

const steps = [
  { key: 'search', label: 'Search' },
  { key: 'select', label: 'Select Novel' },
  { key: 'download', label: 'Download' },
  { key: 'complete', label: 'Complete' }
];

const DownloadStepper = ({ activeStep }: DownloadStepperProps) => {
  // Convert activeStep string to numeric index
  const currentStep = steps.findIndex((step) => step.key === activeStep);

  return (
    <Paper sx={{ p: 2, mb: 3 }} elevation={1}>
      <Box sx={{ width: '100%' }}>
        <Stepper activeStep={currentStep} alternativeLabel>
          {steps.map((step) => (
            <Step key={step.key}>
              <StepLabel>{step.label}</StepLabel>
            </Step>
          ))}
        </Stepper>
      </Box>
    </Paper>
  );
};

export default DownloadStepper;
