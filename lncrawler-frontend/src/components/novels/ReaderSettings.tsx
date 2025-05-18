import React, { useState } from 'react';
import {
  Drawer, Box, Typography, IconButton, Divider, Button, Slider,
  FormControl, InputLabel, Select, MenuItem, ToggleButtonGroup, ToggleButton,
  Popover, useTheme, useMediaQuery, SelectChangeEvent,
  Grid2 as Grid, Switch, FormControlLabel,
} from '@mui/material';
import { ColorResult, ChromePicker } from 'react-color';
import Cookies from 'js-cookie';
import FormatAlignLeftIcon from '@mui/icons-material/FormatAlignLeft';
import FormatAlignCenterIcon from '@mui/icons-material/FormatAlignCenter';
import FormatAlignJustifyIcon from '@mui/icons-material/FormatAlignJustify';
import FormatAlignRightIcon from '@mui/icons-material/ArrowForward';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import HomeIcon from '@mui/icons-material/Home';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import CloseIcon from '@mui/icons-material/Close';
import ClearIcon from '@mui/icons-material/Clear';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import VerticalAlignTopIcon from '@mui/icons-material/VerticalAlignTop';
import VerticalAlignBottomIcon from '@mui/icons-material/VerticalAlignBottom';
import BlockIcon from '@mui/icons-material/Block';

// Define constants for cookie names
const COOKIE_PREFIX = 'lncrawler_reader_';
const COOKIE_EXPIRY = 365; // days

export type EdgeTapBehavior = 'none' | 'scrollUp' | 'scrollDown' | 'chapter';

export interface ReaderSettings {
  fontSize: number;
  fontFamily: string | null;
  textAlign: 'left' | 'center' | 'justify' | 'right';
  fontColor: string | null;
  backgroundColor: string | null;
  margin: number;
  lineSpacing: number;
  readingMode: 'classic' | 'manga' | 'mangaReversed' | 'webtoon';
  dimLevel: number;
  leftEdgeTapBehavior: EdgeTapBehavior;
  rightEdgeTapBehavior: EdgeTapBehavior;
  textSelectable: boolean;
  savePosition: boolean;
}

// Default settings
export const defaultSettings: ReaderSettings = {
  fontSize: 18,
  fontFamily: null,
  textAlign: 'justify',
  fontColor: null,
  backgroundColor: null,
  margin: 0,
  lineSpacing: 1.6,
  readingMode: 'classic',
  dimLevel: 0,
  leftEdgeTapBehavior: 'none',
  rightEdgeTapBehavior: 'none',
  textSelectable: true,
  savePosition: true,
};

export interface ChapterInfo {
  title: string;
  novelTitle: string;
  prevChapter?: number | null;
  nextChapter?: number | null;
}

interface ReaderSettingsProps {
  open: boolean;
  onClose: () => void;
  settings: ReaderSettings;
  onSettingChange: (settings: ReaderSettings) => void;
  chapterInfo: ChapterInfo;
  onNavigate: (type: 'prev' | 'home' | 'next') => void;
}

interface FontOption {
  name: string;
  value: string | null;
}

const fontOptions: FontOption[] = [
  { name: 'Default (theme font)', value: null },
  { name: 'Arial', value: 'Arial, sans-serif' },
  { name: 'Times New Roman', value: 'Times New Roman, serif' },
  { name: 'Georgia', value: 'Georgia, serif' },
  { name: 'Verdana', value: 'Verdana, sans-serif' },
  { name: 'OpenDyslexic', value: 'OpenDyslexic, cursive' },
  { name: 'Roboto', value: 'Roboto, sans-serif' },
];

const readingModeOptions = [
  { name: 'Classic', value: 'classic' },
  { name: 'Manga', value: 'manga' },
  { name: 'Manga Reversed', value: 'mangaReversed' },
  { name: 'Webtoon', value: 'webtoon' },
];

const edgeTapOptions = [
  { name: 'Do Nothing', value: 'none', icon: BlockIcon },
  { name: 'Scroll Up', value: 'scrollUp', icon: VerticalAlignTopIcon },
  { name: 'Scroll Down', value: 'scrollDown', icon: VerticalAlignBottomIcon },
  { name: 'Change Chapter', value: 'chapter', icon: ChevronRightIcon },
];

const ReaderSettings = ({
  open,
  onClose,
  settings,
  onSettingChange,
  chapterInfo,
  onNavigate,
}: ReaderSettingsProps) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  
  const [showFontColorPicker, setShowFontColorPicker] = useState(false);
  const [showBgColorPicker, setShowBgColorPicker] = useState(false);
  const [fontColorAnchor, setFontColorAnchor] = useState<HTMLButtonElement | null>(null);
  const [bgColorAnchor, setBgColorAnchor] = useState<HTMLButtonElement | null>(null);

  const handleFontSizeChange = (_event: Event, newValue: number | number[]) => {
    const newSettings = { ...settings, fontSize: newValue as number };
    onSettingChange(newSettings);
    saveSetting('fontSize', newValue as number);
  };

  const handleFontFamilyChange = (event: SelectChangeEvent) => {
    const value = event.target.value === "null" ? null : event.target.value;
    const newSettings = { ...settings, fontFamily: value };
    onSettingChange(newSettings);
    saveSetting('fontFamily', value);
  };

  const handleTextAlignChange = (_event: React.MouseEvent<HTMLElement>, newValue: string | null) => {
    if (newValue !== null) {
      const newSettings = { ...settings, textAlign: newValue as 'left' | 'center' | 'justify' | 'right' };
      onSettingChange(newSettings);
      saveSetting('textAlign', newValue);
    }
  };

  const handleFontColorChange = (color: ColorResult) => {
    const newSettings = { ...settings, fontColor: color.hex };
    onSettingChange(newSettings);
    saveSetting('fontColor', color.hex);
  };

  const handleBackgroundColorChange = (color: ColorResult) => {
    const newSettings = { ...settings, backgroundColor: color.hex };
    onSettingChange(newSettings);
    saveSetting('backgroundColor', color.hex);
  };

  const resetFontColor = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    const newSettings = { ...settings, fontColor: null };
    onSettingChange(newSettings);
    saveSetting('fontColor', null);
    setShowFontColorPicker(false);
  };

  const resetBackgroundColor = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    const newSettings = { ...settings, backgroundColor: null };
    onSettingChange(newSettings);
    saveSetting('backgroundColor', null);
    setShowBgColorPicker(false);
  };

  const handleMarginChange = (_event: Event, newValue: number | number[]) => {
    const newSettings = { ...settings, margin: newValue as number };
    onSettingChange(newSettings);
    saveSetting('margin', newValue as number);
  };

  const handleLineSpacingChange = (_event: Event, newValue: number | number[]) => {
    const newSettings = { ...settings, lineSpacing: newValue as number };
    onSettingChange(newSettings);
    saveSetting('lineSpacing', newValue as number);
  };

  const handleReadingModeChange = (event: SelectChangeEvent) => {
    const newSettings = { ...settings, readingMode: event.target.value as any };
    onSettingChange(newSettings);
    saveSetting('readingMode', event.target.value);
  };

  const handleDimLevelChange = (_event: Event, newValue: number | number[]) => {
    const newSettings = { ...settings, dimLevel: newValue as number };
    onSettingChange(newSettings);
    saveSetting('dimLevel', newValue as number);
  };

  const handleEdgeTapChange = (edge: 'left' | 'right', value: EdgeTapBehavior) => {
    const key = edge === 'left' ? 'leftEdgeTapBehavior' : 'rightEdgeTapBehavior';
    const newSettings = { ...settings, [key]: value };
    onSettingChange(newSettings);
    saveSetting(key, value);
  };

  const handleTextSelectableChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const newSettings = { ...settings, textSelectable: event.target.checked };
    onSettingChange(newSettings);
    saveSetting('textSelectable', event.target.checked);
  };

  const handleSavePositionChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const newSettings = { ...settings, savePosition: event.target.checked };
    onSettingChange(newSettings);
    saveSetting('savePosition', event.target.checked);
  };

  const saveSetting = (key: string, value: any) => {
    Cookies.set(COOKIE_PREFIX + key, JSON.stringify(value), { expires: COOKIE_EXPIRY });
  };

  const resetDefaults = () => {
    onSettingChange(defaultSettings);
    Object.entries(defaultSettings).forEach(([key, value]) => {
      saveSetting(key, value);
    });
  };

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

  return (
    <Drawer 
      anchor={isMobile ? "bottom" : "right"} 
      open={open} 
      onClose={onClose}
      PaperProps={{
        sx: {
          width: isMobile ? '100%' : '350px',
          maxHeight: isMobile ? '60vh' : '100%',
          borderTopLeftRadius: isMobile ? '16px' : 0,
          borderTopRightRadius: isMobile ? '16px' : 0,
          padding: 2,
          overflow: 'auto',
          zIndex: theme.zIndex.drawer,
          boxShadow: 3,
        }
      }}
    >
      <Box sx={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        mx: -2,
        mt: -2,
        p: 2,
        pb: 0.5,
        position: 'sticky',
        top: "-30px",
        width: 'calc(100% + 32px)',
        zIndex: 2,
        backgroundColor: theme.palette.background.paper,
      }}>
        <Typography variant="h6">Reader Settings</Typography>
        <IconButton onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </Box>

      <Divider sx={{ mb: 2 }} />

      {/* Navigation Controls */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'medium' }}>Chapter Navigation</Typography>
        <Grid container spacing={1}>
          <Grid size={4}>
            <Button 
              fullWidth 
              variant={chapterInfo.prevChapter ? "contained" : "outlined"}
              color={chapterInfo.prevChapter ? "primary" : "inherit"}
              startIcon={<ArrowBackIcon />}
              onClick={() => onNavigate('prev')}
              disabled={!chapterInfo.prevChapter}
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
              onClick={() => onNavigate('home')}
              size="medium"
            >
              Home
            </Button>
          </Grid>
          <Grid size={4}>
            <Button 
              fullWidth 
              variant={chapterInfo.nextChapter ? "contained" : "outlined"}
              color={chapterInfo.nextChapter ? "primary" : "inherit"}
              endIcon={<ArrowForwardIcon />}
              onClick={() => onNavigate('next')}
              disabled={!chapterInfo.nextChapter}
              size="medium"
            >
              Next
            </Button>
          </Grid>
        </Grid>
      </Box>

      <Divider sx={{ mb: 2 }} />

      {/* Font Settings */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>Font Size: {settings.fontSize}px</Typography>
        <Slider
          value={settings.fontSize}
          onChange={handleFontSizeChange}
          min={12}
          max={32}
          step={1}
          marks={[
            { value: 12.5, label: '12px' },
            { value: 22, label: '22px' },
            { value: 31.5, label: '32px' },
          ]}
          valueLabelDisplay="auto"
        />
      </Box>

      <Box sx={{ mb: 2 }}>
        <FormControl fullWidth variant="outlined" size="small">
          <InputLabel>Font</InputLabel>
          <Select
            value={settings.fontFamily === null ? "null" : settings.fontFamily}
            onChange={handleFontFamilyChange}
            label="Font"
          >
            {fontOptions.map((font) => (
              <MenuItem 
                key={font.name} 
                value={font.value === null ? "null" : font.value}
                style={{ fontFamily: font.value || undefined }}
              >
                {font.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>

      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>Text Alignment</Typography>
        <ToggleButtonGroup
          value={settings.textAlign}
          exclusive
          onChange={handleTextAlignChange}
          aria-label="text alignment"
          fullWidth
          size="small"
        >
          <ToggleButton value="left" aria-label="left aligned">
            <FormatAlignLeftIcon />
          </ToggleButton>
          <ToggleButton value="center" aria-label="centered">
            <FormatAlignCenterIcon />
          </ToggleButton>
          <ToggleButton value="justify" aria-label="justified">
            <FormatAlignJustifyIcon />
          </ToggleButton>
          <ToggleButton value="right" aria-label="right aligned">
            <FormatAlignRightIcon />
          </ToggleButton>
        </ToggleButtonGroup>
      </Box>

      <Divider sx={{ mb: 2 }} />

      {/* Color Settings */}
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
                  borderColor: settings.fontColor || theme.palette.text.primary,
                  color: settings.fontColor || theme.palette.text.primary,
                  '&:hover': {
                    borderColor: settings.fontColor || theme.palette.text.primary,
                  },
                  pr: settings.fontColor ? 5 : 2,
                }}
              >
                Text Color
              </Button>
              {settings.fontColor && (
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
                color={settings.fontColor || theme.palette.text.primary} 
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
                  borderColor: settings.backgroundColor || theme.palette.background.paper,
                  backgroundColor: settings.backgroundColor || theme.palette.background.paper,
                  '&:hover': {
                    borderColor: 'primary.main',
                    backgroundColor: settings.backgroundColor || theme.palette.background.paper,
                  },
                  pr: settings.backgroundColor ? 5 : 2,
                }}
              >
                Background
              </Button>
              {settings.backgroundColor && (
                <IconButton 
                  size="small" 
                  onClick={resetBackgroundColor}
                  sx={{
                    position: 'absolute',
                    right: 8,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    zIndex: 1,
                    color: theme.palette.getContrastText(settings.backgroundColor || '#fff'),
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
                color={settings.backgroundColor || theme.palette.background.paper} 
                onChange={handleBackgroundColorChange}
                disableAlpha={true}
              />
            </Popover>
          </Grid>
        </Grid>
      </Box>

      {/* Layout Settings */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>Margin: {settings.margin}%</Typography>
        <Slider
          value={settings.margin}
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
        <Typography variant="subtitle1" gutterBottom>Line Spacing: {settings.lineSpacing}</Typography>
        <Slider
          value={settings.lineSpacing}
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
      
      {/* Dim Level Slider */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>Screen Dim: {settings.dimLevel}%</Typography>
        <Slider
          value={settings.dimLevel}
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

      <Box sx={{ mb: 2 }}>
        <FormControl fullWidth variant="outlined" size="small">
          <InputLabel>Reading Mode</InputLabel>
          <Select
            value={settings.readingMode}
            onChange={handleReadingModeChange}
            label="Reading Mode"
          >
            {readingModeOptions.map((mode) => (
              <MenuItem key={mode.value} value={mode.value}>
                {mode.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>

      <Divider sx={{ my: 2 }} />

      {/* Text Selection and Position Toggles */}
      <Box sx={{ mb: 3 }}>
        <FormControlLabel
          control={
            <Switch
              checked={settings.textSelectable}
              onChange={handleTextSelectableChange}
              color="primary"
            />
          }
          label="Allow Text Selection/Copy"
        />
        <FormControlLabel
          control={
            <Switch
              checked={settings.savePosition}
              onChange={handleSavePositionChange}
              color="primary"
            />
          }
          label="Remember Reading Position"
        />
      </Box>

      {/* Edge Tap Behavior */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="subtitle1" gutterBottom>Edge Tap Behavior</Typography>
        <Grid container spacing={2}>
          <Grid size={6}>
            <Typography variant="body2" color="text.secondary" align="center" gutterBottom>
              Left Edge
            </Typography>
            <FormControl fullWidth size="small">
              <Select
                value={settings.leftEdgeTapBehavior}
                onChange={(e) => handleEdgeTapChange('left', e.target.value as EdgeTapBehavior)}
                displayEmpty
                renderValue={(selected) => {
                  const option = edgeTapOptions.find(opt => opt.value === selected);
                  return (
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      {option && React.createElement(option.icon, { sx: { mr: 1, fontSize: '1.2rem' } })}
                      <Typography variant="body2" noWrap>
                        {option ? option.name : ''}
                      </Typography>
                    </Box>
                  );
                }}
              >
                {edgeTapOptions.map((option) => (
                  <MenuItem key={`left-${option.value}`} value={option.value}>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      {React.createElement(option.icon, { sx: { mr: 1, fontSize: '1.2rem' } })}
                      {option.name}
                    </Box>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid size={6}>
            <Typography variant="body2" color="text.secondary" align="center" gutterBottom>
              Right Edge
            </Typography>
            <FormControl fullWidth size="small">
              <Select
                value={settings.rightEdgeTapBehavior}
                onChange={(e) => handleEdgeTapChange('right', e.target.value as EdgeTapBehavior)}
                displayEmpty
                renderValue={(selected) => {
                  const option = edgeTapOptions.find(opt => opt.value === selected);
                  return (
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      {option && React.createElement(option.icon, { sx: { mr: 1, fontSize: '1.2rem' } })}
                      <Typography variant="body2" noWrap>
                        {option ? option.name : ''}
                      </Typography>
                    </Box>
                  );
                }}
              >
                {edgeTapOptions.map((option) => (
                  <MenuItem key={`right-${option.value}`} value={option.value}>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      {React.createElement(option.icon, { sx: { mr: 1, fontSize: '1.2rem' } })}
                      {option.name}
                    </Box>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
        </Grid>
      </Box>

      {/* Reset Button */}
      <Button
        variant="contained"
        color="secondary"
        fullWidth
        onClick={resetDefaults}
      >
        Reset to Defaults
      </Button>
    </Drawer>
  );
};

export default ReaderSettings;
