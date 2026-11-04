import { Box, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useReaderSettings } from '../hooks/useReaderSettings';
import { paragraphIndentFor, readerTextStyles } from '../content/readerTextStyles';
import { useSiteTheme } from '../theme/siteTheme';
import { useSettingsContext } from './settingsContext';

// A sample chapter set in the current settings, with the dim and night filters over it.
// Hidden from assistive technology: the controls around it say what they do.
const SimulatedPreview = () => {
  const { t } = useTranslation();
  const settings = useReaderSettings();
  const { mode } = useSettingsContext();
  const theme = useSiteTheme();
  // Same fallbacks as the reader's theme choices
  const background = settings.backgroundColor ?? theme.palette.background.paper;
  const color = settings.fontColor ?? theme.palette.text.primary;

  return (
    <Box
      aria-hidden="true"
      sx={{
        position: 'relative',
        overflow: 'hidden',
        maxHeight: 240,
        borderRadius: 2,
        border: 1,
        borderColor: 'divider',
        background,
        color,
        px: 2,
        pt: 2,
        pb: 6,
        // Stays in view while the page is scrolled, except in landscape where it would take too much height
        ...(mode === 'phone' && { position: 'sticky', top: 0, zIndex: 1 }),
      }}
    >
      <Typography sx={{ fontWeight: 700, mb: 1 }}>{t('readerSettingsPages.previewTitle')}</Typography>
      <Box sx={{ mx: `${settings.margin}%` }}>
        <Typography component="div" sx={readerTextStyles(settings)}>
          <p>{t('readerDisplay.preview.sample')}</p>
          {/* Like the chapter, the indent skips the first paragraph */}
          <p style={{ textIndent: paragraphIndentFor(settings.paragraphIndent) }}>{t('readerSettingsPages.previewText')}</p>
        </Typography>
      </Box>
      <Box sx={{ position: 'absolute', insetInline: 0, bottom: 0, height: 48, background: `linear-gradient(transparent, ${background})`, pointerEvents: 'none' }} />
      {settings.dimLevel > 0 && (
        <Box sx={{ position: 'absolute', inset: 0, backgroundColor: 'black', opacity: settings.dimLevel / 100, pointerEvents: 'none' }} />
      )}
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          backgroundColor: '#ffb347',
          mixBlendMode: 'multiply',
          opacity: settings.nightMode ? settings.nightModeStrength / 100 : 0,
          pointerEvents: 'none',
        }}
      />
    </Box>
  );
};

export default SimulatedPreview;
