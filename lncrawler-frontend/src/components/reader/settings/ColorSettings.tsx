import React, { useState } from 'react';
import {
  Box,
  Typography,
  Button,
  IconButton,
  Popover,
  Grid2 as Grid,
  useTheme,
  Switch,
  FormControlLabel,
  TextField,
  Divider,
} from '@mui/material';
import { ChromePicker, ColorResult } from 'react-color';
import ClearIcon from '@mui/icons-material/Clear';
import MobileSafeSlider from '../../common/MobileSafeSlider';

interface ColorSettingsProps {
  fontColor: string | null;
  backgroundColor: string | null;
  dimLevel: number;
  nightMode: boolean;
  nightModeStrength: number;
  nightModeScheduleEnabled: boolean;
  nightModeStartTime: string;
  nightModeEndTime: string;
  onFontColorChange: (color: string | null) => void;
  onBackgroundColorChange: (color: string | null) => void;
  onDimLevelChange: (level: number) => void;
  onNightModeChange: (enabled: boolean) => void;
  onNightModeStrengthChange: (strength: number) => void;
  onNightModeScheduleChange: (enabled: boolean) => void;
  onNightModeStartTimeChange: (time: string) => void;
  onNightModeEndTimeChange: (time: string) => void;
}

/**
 * Component for color-related reader settings
 */
const ColorSettings: React.FC<ColorSettingsProps> = ({
  fontColor,
  backgroundColor,
  dimLevel,
  nightMode,
  nightModeStrength,
  nightModeScheduleEnabled,
  nightModeStartTime,
  nightModeEndTime,
  onFontColorChange,
  onBackgroundColorChange,
  onDimLevelChange,
  onNightModeChange,
  onNightModeStrengthChange,
  onNightModeScheduleChange,
  onNightModeStartTimeChange,
  onNightModeEndTimeChange,
}) => {
  const theme = useTheme();
  const [showFontColorPicker, setShowFontColorPicker] = useState(false);
  const [showBgColorPicker, setShowBgColorPicker] = useState(false);
  const [fontColorAnchor, setFontColorAnchor] = useState<HTMLButtonElement | null>(null);
  const [bgColorAnchor, setBgColorAnchor] = useState<HTMLButtonElement | null>(null);

  const handleFontColorClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    setFontColorAnchor(event.currentTarget);
    setShowFontColorPicker(true);
  };

  const handleBgColorClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    setBgColorAnchor(event.currentTarget);
    setShowBgColorPicker(true);
  };

  const closeFontColorPicker = () => {
    setShowFontColorPicker(false);
    setFontColorAnchor(null);
  };

  const closeBgColorPicker = () => {
    setShowBgColorPicker(false);
    setBgColorAnchor(null);
  };

  const handleFontColorChange = (color: ColorResult) => {
    onFontColorChange(color.hex);
  };

  const handleBackgroundColorChange = (color: ColorResult) => {
    onBackgroundColorChange(color.hex);
  };

  const resetFontColor = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    onFontColorChange(null);
    setShowFontColorPicker(false);
  };

  const resetBackgroundColor = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    onBackgroundColorChange(null);
    setShowBgColorPicker(false);
  };

  const handleDimLevelChange = (_event: Event, newValue: number | number[]) => {
    onDimLevelChange(newValue as number);
  };

  const handleNightModeToggle = (event: React.ChangeEvent<HTMLInputElement>) => {
    onNightModeChange(event.target.checked);
  };

  const handleNightModeStrengthChange = (_event: Event, newValue: number | number[]) => {
    onNightModeStrengthChange(newValue as number);
  };

  const handleNightModeScheduleToggle = (event: React.ChangeEvent<HTMLInputElement>) => {
    onNightModeScheduleChange(event.target.checked);
  };

  const handleStartTimeChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onNightModeStartTimeChange(event.target.value);
  };

  const handleEndTimeChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onNightModeEndTimeChange(event.target.value);
  };

  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle1" gutterBottom>Colors</Typography>
      <Grid container spacing={2}>
        <Grid size={6}>
          <Box sx={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <Button
              variant="outlined"
              fullWidth
              onClick={handleFontColorClick}
              sx={{
                borderColor: fontColor || theme.palette.text.primary,
                color: fontColor || theme.palette.text.primary,
                '&:hover': {
                  borderColor: fontColor || theme.palette.text.primary,
                },
                pr: fontColor ? 5 : 2,
              }}
            >
              Text Color
            </Button>
            {fontColor && (
              <IconButton 
                size="small" 
                onClick={resetFontColor}
                sx={{
                  position: 'absolute',
                  right: 8,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  zIndex: 1,
                }}
              >
                <ClearIcon fontSize="small" />
              </IconButton>
            )}
          </Box>
          <Popover
            open={showFontColorPicker}
            anchorEl={fontColorAnchor}
            onClose={closeFontColorPicker}
            anchorOrigin={{
              vertical: 'bottom',
              horizontal: 'center',
            }}
            transformOrigin={{
              vertical: 'top',
              horizontal: 'center',
            }}
            sx={{ 
              zIndex: theme.zIndex.drawer + 1,
              '& .chrome-picker': {
                boxShadow: 'none !important',
              }
            }}
            disablePortal={false}
          >
            <ChromePicker 
              color={fontColor || theme.palette.text.primary} 
              onChange={handleFontColorChange}
              disableAlpha={true}
            />
          </Popover>
        </Grid>
        <Grid size={6}>
          <Box sx={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <Button
              variant="outlined"
              fullWidth
              onClick={handleBgColorClick}
              sx={{
                borderColor: backgroundColor || theme.palette.background.paper,
                backgroundColor: backgroundColor || theme.palette.background.paper,
                '&:hover': {
                  borderColor: 'primary.main',
                  backgroundColor: backgroundColor || theme.palette.background.paper,
                },
                pr: backgroundColor ? 5 : 2,
              }}
            >
              Background
            </Button>
            {backgroundColor && (
              <IconButton 
                size="small" 
                onClick={resetBackgroundColor}
                sx={{
                  position: 'absolute',
                  right: 8,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  zIndex: 1,
                  color: theme.palette.getContrastText(backgroundColor || '#fff'),
                }}
              >
                <ClearIcon fontSize="small" />
              </IconButton>
            )}
          </Box>
          <Popover
            open={showBgColorPicker}
            anchorEl={bgColorAnchor}
            onClose={closeBgColorPicker}
            anchorOrigin={{
              vertical: 'bottom',
              horizontal: 'center',
            }}
            transformOrigin={{
              vertical: 'top',
              horizontal: 'center',
            }}
            sx={{ 
              zIndex: theme.zIndex.drawer + 1,
              '& .chrome-picker': {
                boxShadow: 'none !important',
              }
            }}
            disablePortal={false}
          >
            <ChromePicker 
              color={backgroundColor || theme.palette.background.paper} 
              onChange={handleBackgroundColorChange}
              disableAlpha={true}
            />
          </Popover>
        </Grid>
      </Grid>

      {/* Dim Level Slider */}
      <Box sx={{ mt: 2 }}>
        <Typography variant="subtitle1" gutterBottom>Screen Dim: {dimLevel}%</Typography>
        <MobileSafeSlider
          value={dimLevel}
          onChange={handleDimLevelChange}
          min={0}
          max={90}
          step={5}
          marks={[
            { value: 2, label: '0%' },
            { value: 45, label: '45%' },
            { value: 88, label: '90%' },
          ]}
          valueLabelDisplay="auto"
        />
      </Box>

      <Divider sx={{ my: 2 }} />

      {/* Night Mode Section */}
      <Box sx={{ mt: 2 }}>
        <FormControlLabel
          control={
            <Switch
              checked={nightMode}
              onChange={handleNightModeToggle}
              color="primary"
            />
          }
          label="Night Mode (Blue Light Filter)"
        />
        
        {nightMode && (
          <Box sx={{ mt: 2, pl: 2 }}>
            {/* Night Mode Strength */}
            <Typography variant="subtitle2" gutterBottom>
              Filter Strength: {nightModeStrength}%
            </Typography>
            <MobileSafeSlider
              value={nightModeStrength}
              onChange={handleNightModeStrengthChange}
              min={10}
              max={90}
              step={5}
              marks={[
                { value: 10, label: '10%' },
                { value: 50, label: '50%' },
                { value: 90, label: '90%' },
              ]}
              valueLabelDisplay="auto"
              sx={{ mb: 2 }}
            />
            
            {/* Schedule Toggle */}
            <FormControlLabel
              control={
                <Switch
                  checked={nightModeScheduleEnabled}
                  onChange={handleNightModeScheduleToggle}
                  color="primary"
                />
              }
              label="Enable Schedule"
              sx={{ mb: 2 }}
            />
            
            {/* Schedule Times */}
            {nightModeScheduleEnabled && (
              <Grid container spacing={2}>
                <Grid size={6}>
                  <TextField
                    label="Start Time"
                    type="time"
                    value={nightModeStartTime}
                    onChange={handleStartTimeChange}
                    InputLabelProps={{
                      shrink: true,
                    }}
                    inputProps={{
                      step: 300, // 5 min
                    }}
                    size="small"
                    fullWidth
                  />
                </Grid>
                <Grid size={6}>
                  <TextField
                    label="End Time"
                    type="time"
                    value={nightModeEndTime}
                    onChange={handleEndTimeChange}
                    InputLabelProps={{
                      shrink: true,
                    }}
                    inputProps={{
                      step: 300, // 5 min
                    }}
                    size="small"
                    fullWidth
                  />
                </Grid>
              </Grid>
            )}
          </Box>
        )}
      </Box>
    </Box>
  );
};

export default ColorSettings;
