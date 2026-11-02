import { createTheme, decomposeColor, getContrastRatio, type Theme } from '@mui/material/styles';

const DARK_TEXT = '#1a1a1a';
const LIGHT_TEXT = '#ffffff';

// Minimum contrast of the accent against its surface (WCAG non-text contrast)
const MIN_ACCENT_CONTRAST = 3;

// Channels of a colour as 0-255 numbers, whatever notation it was written in
const channels = (color: string): [number, number, number] => {
  const [r, g, b] = decomposeColor(color).values;
  return [r, g, b];
};

// Moves colour a toward colour b by t (0 keeps a, 1 gives b), as a hex string
export function mixColors(a: string, b: string, t: number): string {
  const from = channels(a);
  const to = channels(b);
  const hex = from.map((channel, i) => Math.round(channel + (to[i] - channel) * t).toString(16).padStart(2, '0'));
  return `#${hex.join('')}`;
}

// Whichever of the two text colours reads better on the background
export function bestTextOn(bg: string): string {
  return getContrastRatio(bg, DARK_TEXT) >= getContrastRatio(bg, LIGHT_TEXT) ? DARK_TEXT : LIGHT_TEXT;
}

// Pushes the accent toward the text colour until it stands out from the surface
export function ensureAccent(accent: string, surface: string, fg: string): string {
  for (let step = 0; step <= 10; step++) {
    const candidate = mixColors(accent, fg, step / 10);
    if (getContrastRatio(candidate, surface) >= MIN_ACCENT_CONTRAST) return candidate;
  }
  return fg;
}

// The site theme restyled for a reader background; the site theme itself when there is no usable background
export function buildReaderControlsTheme(siteTheme: Theme, backgroundColor: string | null): Theme {
  if (!backgroundColor) return siteTheme;

  try {
    decomposeColor(backgroundColor);
  } catch {
    return siteTheme;
  }

  const bg = backgroundColor;
  const fg = bestTextOn(bg);
  const accent = ensureAccent(siteTheme.palette.primary.main, bg, fg);

  return createTheme(siteTheme, {
    palette: {
      mode: fg === LIGHT_TEXT ? 'dark' : 'light',
      background: { default: bg, paper: bg },
      text: { primary: fg, secondary: mixColors(fg, bg, 0.28) },
      divider: mixColors(bg, fg, 0.18),
      action: {
        active: mixColors(fg, bg, 0.2),
        hover: mixColors(bg, fg, 0.09),
        selected: mixColors(bg, fg, 0.14),
        disabled: mixColors(fg, bg, 0.6),
        disabledBackground: mixColors(bg, fg, 0.12),
        focus: mixColors(bg, fg, 0.14),
      },
      primary: { main: accent, contrastText: bestTextOn(accent) },
    },
  });
}
