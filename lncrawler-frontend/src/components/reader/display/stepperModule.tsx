import type { ReactNode } from 'react';
import { Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import Stepper from './Stepper';
import { STEPPER_SPECS } from './stepperSpecs';

// The stepper of one stepped number setting as a display module, named by its label key
export const stepperModule = (
  specKey: keyof typeof STEPPER_SPECS,
  labelKey: string,
  buttons?: { decreaseLabel?: ReactNode; increaseLabel?: ReactNode },
) => {
  const StepperModule = () => {
    const { t } = useTranslation();
    return <Stepper settingKey={specKey} {...STEPPER_SPECS[specKey]} label={t(labelKey)} {...buttons} />;
  };
  return StepperModule;
};

// The size module's buttons are a small and a large A
export const SIZE_BUTTONS = {
  decreaseLabel: <Typography component="span" sx={{ fontSize: '0.85rem', lineHeight: 1 }}>A</Typography>,
  increaseLabel: <Typography component="span" sx={{ fontSize: '1.4rem', lineHeight: 1 }}>A</Typography>,
};
