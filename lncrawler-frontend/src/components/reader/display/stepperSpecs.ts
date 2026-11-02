// Step, range and readout of each stepped number setting, shared by the display modules and the settings pages.
// The ranges match readerSettingsSchema.
export const STEPPER_SPECS = {
  fontSize: { step: 1, min: 12, max: 32, format: (value: number) => `${value}px` },
  lineSpacing: { step: 0.1, min: 1, max: 3, format: (value: number) => `${value.toFixed(1)}×` },
  paragraphSpacing: { step: 0.1, min: 1, max: 3, format: (value: number) => `${value.toFixed(1)}×` },
  margin: { step: 1, min: -2, max: 22, format: (value: number) => `${value}%` },
  wordSpacing: { step: 0.5, min: -2, max: 10, format: (value: number) => `${value}px` },
  letterSpacing: { step: 0.1, min: -1, max: 5, format: (value: number) => `${value.toFixed(1)}px` },
  dimLevel: { step: 5, min: 0, max: 90, format: (value: number) => `${value}%` },
  nightModeStrength: { step: 5, min: 10, max: 90, format: (value: number) => `${value}%` },
};
