import { describe, it, expect } from 'vitest';
import { createTheme, getContrastRatio } from '@mui/material/styles';
import { bestTextOn, buildReaderControlsTheme, ensureAccent, mixColors } from './readerControlsTheme';

const siteTheme = createTheme();

describe('mixColors', () => {
  it('returns the start colour at t=0 and the end colour at t=1', () => {
    expect(mixColors('#000000', '#ffffff', 0)).toBe('#000000');
    expect(mixColors('#000000', '#ffffff', 1)).toBe('#ffffff');
  });

  it('blends channels and returns a hex string', () => {
    expect(mixColors('#000000', '#ffffff', 0.5)).toBe('#808080');
  });
});

describe('bestTextOn', () => {
  it('picks white on dark backgrounds and near-black on light ones', () => {
    expect(bestTextOn('#0f1b2d')).toBe('#ffffff');
    expect(bestTextOn('#f4ecd8')).toBe('#1a1a1a');
  });
});

describe('ensureAccent', () => {
  it('pushes a low-contrast accent until it reaches 3:1 against the surface', () => {
    const accent = ensureAccent('#eeeeee', '#ffffff', '#1a1a1a');
    expect(getContrastRatio(accent, '#ffffff')).toBeGreaterThanOrEqual(3);
  });
});

describe('buildReaderControlsTheme', () => {
  it('gives white text and dark mode on a dark background', () => {
    const theme = buildReaderControlsTheme(siteTheme, '#1a1a1a');
    expect(theme.palette.mode).toBe('dark');
    expect(theme.palette.text.primary).toBe('#ffffff');
    expect(theme.palette.background.paper).toBe('#1a1a1a');
  });

  it('gives near-black text and light mode on a light background', () => {
    const theme = buildReaderControlsTheme(siteTheme, '#ffffff');
    expect(theme.palette.mode).toBe('light');
    expect(theme.palette.text.primary).toBe('#1a1a1a');
  });

  it('keeps the primary accent at 3:1 or better against the background', () => {
    const lowContrast = createTheme({ palette: { primary: { main: '#eeeeee' } } });
    const theme = buildReaderControlsTheme(lowContrast, '#ffffff');
    expect(getContrastRatio(theme.palette.primary.main, '#ffffff')).toBeGreaterThanOrEqual(3);
  });

  it('tints the action colours from the text and background, so icons and toggles stay visible on dark backgrounds', () => {
    const theme = buildReaderControlsTheme(siteTheme, '#1a1a1a');
    expect(theme.palette.action.active).toBe(mixColors('#ffffff', '#1a1a1a', 0.2));
    expect(theme.palette.action.disabled).toBe(mixColors('#ffffff', '#1a1a1a', 0.6));
    expect(theme.palette.action.disabledBackground).toBe(mixColors('#1a1a1a', '#ffffff', 0.12));
    expect(theme.palette.action.focus).toBe(mixColors('#1a1a1a', '#ffffff', 0.14));
    expect(getContrastRatio(theme.palette.action.active, '#1a1a1a')).toBeGreaterThanOrEqual(4.5);
  });

  it('returns the site theme itself when the background is null', () => {
    expect(buildReaderControlsTheme(siteTheme, null)).toBe(siteTheme);
  });

  it('returns the site theme itself when the background is not a colour', () => {
    expect(buildReaderControlsTheme(siteTheme, 'not-a-colour')).toBe(siteTheme);
  });
});
