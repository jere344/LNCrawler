import type { SxProps, Theme } from '@mui/material';
import type { ReaderSettings } from '../readerSettingsSchema';

// First-line indent of a paragraph. The chapter body, the settings preview and the sheet preview all read it from here.
export const PARAGRAPH_INDENT = '2em';

export const paragraphIndentFor = (enabled: boolean): string => (enabled ? PARAGRAPH_INDENT : '0');

// Text styles of the chapter body and the settings preview, so the two cannot diverge.
export const readerTextStyles = (settings: ReaderSettings): SxProps<Theme> => ({
  fontSize: `${settings.fontSize}px`,
  lineHeight: settings.lineSpacing,
  wordSpacing: `${settings.wordSpacing}px`,
  letterSpacing: `${settings.letterSpacing}px`,
  textAlign: settings.textAlign,
  // Crawled text often joins words with &nbsp;, which would otherwise widen the page on phones
  overflowWrap: 'break-word',
  fontFamily: settings.fontFamily || undefined,
  userSelect: settings.textSelectable ? 'text' : 'none',
  WebkitUserSelect: settings.textSelectable ? 'text' : 'none',
  MozUserSelect: settings.textSelectable ? 'text' : 'none',
  msUserSelect: settings.textSelectable ? 'text' : 'none',
  '& p': {
    marginBottom: `${settings.paragraphSpacing}em`,
  },
});
