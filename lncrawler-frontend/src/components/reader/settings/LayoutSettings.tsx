import React from 'react';
import {
  Box,
  Typography,
  FormControlLabel,
  Switch,
} from '@mui/material';
import MobileSafeSlider from '../../common/MobileSafeSlider';

interface LayoutSettingsProps {
  margin: number;
  lineSpacing: number;
  wordSpacing: number;
  letterSpacing: number;
  hideScrollbar: boolean;
  paragraphIndent: boolean;
  paragraphSpacing: number;
  onMarginChange: (margin: number) => void;
  onLineSpacingChange: (spacing: number) => void;
  onWordSpacingChange: (spacing: number) => void;
  onLetterSpacingChange: (spacing: number) => void;
  onHideScrollbarChange: (hide: boolean) => void;
  onParagraphIndentChange: (indent: boolean) => void;
  onParagraphSpacingChange: (spacing: number) => void;
}


/**
 * Component for layout-related reader settings
 */
const LayoutSettings: React.FC<LayoutSettingsProps> = ({
  margin,
  lineSpacing,
  wordSpacing,
  letterSpacing,
  hideScrollbar,
  paragraphIndent,
  paragraphSpacing,
  onMarginChange,
  onLineSpacingChange,
  onWordSpacingChange,
  onLetterSpacingChange,
  onHideScrollbarChange,
  onParagraphIndentChange,
  onParagraphSpacingChange,
}) => {
  const handleMarginChange = (_event: Event, newValue: number | number[]) => {
    onMarginChange(newValue as number);
  };

  const handleLineSpacingChange = (_event: Event, newValue: number | number[]) => {
    onLineSpacingChange(newValue as number);
  };

  const handleWordSpacingChange = (_event: Event, newValue: number | number[]) => {
    onWordSpacingChange(newValue as number);
  };

  const handleLetterSpacingChange = (_event: Event, newValue: number | number[]) => {
    onLetterSpacingChange(newValue as number);
  };

  const handleHideScrollbarChange = (_event: React.ChangeEvent<HTMLInputElement>, checked: boolean) => {
    onHideScrollbarChange(checked);
  };

  const handleParagraphIndentChange = (_event: React.ChangeEvent<HTMLInputElement>, checked: boolean) => {
    onParagraphIndentChange(checked);
  };

  const handleParagraphSpacingChange = (_event: Event, newValue: number | number[]) => {
    onParagraphSpacingChange(newValue as number);
  };

  return (
    <>
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>Margin: {margin}%</Typography>
        <MobileSafeSlider
          value={margin}
          onChange={handleMarginChange}
          min={-2}
          max={22}
          step={1}
          marks={[
            { value: -1.5, label: '-2%' },
            { value: 10, label: '10%' },
            { value: 21.5, label: '22%' },
          ]}
          valueLabelDisplay="auto"
        />
      </Box>

      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>Line Spacing: {lineSpacing}</Typography>
        <MobileSafeSlider
          value={lineSpacing}
          onChange={handleLineSpacingChange}
          min={1}
          max={3}
          step={0.1}
          marks={[
            { value: 1.02, label: '1x' },
            { value: 2, label: '2x' },
            { value: 2.98, label: '3x' },
          ]}
          valueLabelDisplay="auto"
        />
      </Box>

      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>Word Spacing: {wordSpacing}px</Typography>
        <MobileSafeSlider
          value={wordSpacing}
          onChange={handleWordSpacingChange}
          min={-2}
          max={10}
          step={0.5}
          marks={[
            { value: -1.75, label: '-2px' },
            { value: 0, label: '0px' },
            { value: 5, label: '5px' },
            { value: 9.75, label: '10px' },
          ]}
          valueLabelDisplay="auto"
        />
      </Box>

      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>Letter Spacing: {letterSpacing}px</Typography>
        <MobileSafeSlider
          value={letterSpacing}
          onChange={handleLetterSpacingChange}
          min={-1}
          max={5}
          step={0.1}
          marks={[
            { value: -0.9, label: '-1px' },
            { value: 0, label: '0px' },
            { value: 2.5, label: '2.5px' },
            { value: 4.9, label: '5px' },
          ]}
          valueLabelDisplay="auto"
        />
      </Box>

      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>Paragraph Spacing: {paragraphSpacing}em</Typography>
        <MobileSafeSlider
          value={paragraphSpacing}
          onChange={handleParagraphSpacingChange}
          min={1}
          max={3}
          step={0.1}
          marks={[
            { value: 1, label: '1em' },
            { value: 2, label: '2em' },
            { value: 2.95, label: '3em' },
          ]}
          valueLabelDisplay="auto"
        />
      </Box>

      <Box sx={{ mb: 2 }}>
        <FormControlLabel
          control={
            <Switch
              checked={paragraphIndent}
              onChange={handleParagraphIndentChange}
              color="primary"
            />
          }
          label="Paragraph Indent"
        />
        <Typography variant="caption" color="text.secondary" display="block">
          Add indentation to the first line of each paragraph
        </Typography>
      </Box>

      <Box sx={{ mb: 2 }}>
        <FormControlLabel
          control={
            <Switch
              checked={hideScrollbar}
              onChange={handleHideScrollbarChange}
              color="primary"
            />
          }
          label="Hide Scrollbar"
        />
        <Typography variant="caption" color="text.secondary" display="block">
          Hide browser scrollbar for a cleaner reading experience
        </Typography>
      </Box>
    </>
  );
};

export default LayoutSettings;
