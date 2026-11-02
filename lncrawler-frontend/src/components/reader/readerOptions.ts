// Font options (value null follows the site theme font)
export const fontOptions = [
  { labelKey: 'fontSettings.defaultThemeFont', value: null },
  { labelKey: 'fontSettings.arial', value: 'Arial, sans-serif' },
  { labelKey: 'fontSettings.timesNewRoman', value: 'Times New Roman, serif' },
  { labelKey: 'fontSettings.georgia', value: 'Georgia, serif' },
  { labelKey: 'fontSettings.verdana', value: 'Verdana, sans-serif' },
  { labelKey: 'fontSettings.openDyslexic', value: 'OpenDyslexic, cursive' },
  { labelKey: 'fontSettings.roboto', value: 'Roboto, sans-serif' },
];

// A reader theme sets the background and the text colour together (null means the site theme)
interface ReaderTheme {
  labelKey: string;
  backgroundColor: string | null;
  fontColor: string | null;
}

export const READER_THEMES: ReaderTheme[] = [
  { labelKey: 'readerDisplay.themes.auto', backgroundColor: null, fontColor: null },
  { labelKey: 'readerDisplay.themes.white', backgroundColor: '#ffffff', fontColor: '#1a1a1a' },
  { labelKey: 'readerDisplay.themes.sepia', backgroundColor: '#f4ecd8', fontColor: '#5b4636' },
  { labelKey: 'readerDisplay.themes.night', backgroundColor: '#0f1b2d', fontColor: '#c9c5bd' },
  { labelKey: 'readerDisplay.themes.dark', backgroundColor: '#1a1a1a', fontColor: '#e8e6e3' },
  { labelKey: 'readerDisplay.themes.black', backgroundColor: '#000000', fontColor: '#c9c5bd' },
];

// Colour swatches offered by the colour fields
export const TEXT_COLOR_PRESETS = ['#000000', '#1a1a1a', '#3b3b3b', '#5b4636', '#1e3a5f', '#2d4a2b', '#6b2d2d', '#c9c5bd', '#e8e6e3', '#ffffff'];
export const BACKGROUND_COLOR_PRESETS = ['#ffffff', '#fdf6e3', '#f4ecd8', '#e8e6e3', '#d9d4c7', '#1a1a1a', '#121212', '#0f1b2d', '#1c2b1f', '#000000'];

const normalizeColor = (color: string | null) => color?.toLowerCase() ?? null;

// The reader theme that matches both colours, if one does
export function findReaderTheme(backgroundColor: string | null, fontColor: string | null): ReaderTheme | undefined {
  return READER_THEMES.find(
    (theme) =>
      normalizeColor(theme.backgroundColor) === normalizeColor(backgroundColor) &&
      normalizeColor(theme.fontColor) === normalizeColor(fontColor)
  );
}
