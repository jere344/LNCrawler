import { Box, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useTranslation } from 'react-i18next';
import { useReaderSettings } from '../hooks/useReaderSettings';
import type { ReaderLayoutMode } from '../hooks/useReaderLayout';
import { useViewportSize } from '../hooks/useViewportSize';
import { paragraphIndentFor } from '../content/readerTextStyles';
import DisplayModuleGrid from './DisplayModuleGrid';
import { sheetHeight } from './displayLayout';

const PREVIEW_HEIGHT = 204;
// Sheet width on each layout; the phone sheet spans the viewport
const SHEET_WIDTH: Record<Exclude<ReaderLayoutMode, 'phone'>, number> = { tablet: 480, phoneLandscape: 360, desktop: 400 };
// Same header and padding as the real sheet, so the scale below matches sheetHeight
const SHEET_HEADER_HEIGHT = 44;
const SHEET_PADDING = 14;

interface SheetPreviewProps {
  mode: ReaderLayoutMode;
}

// A snippet of chapter text in the current reader colours, with the sheet's controls laid over it. Decorative: inert and hidden from assistive tech.
const SheetPreview = ({ mode }: SheetPreviewProps) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const settings = useReaderSettings();
  const { width: viewportWidth, height: viewportHeight } = useViewportSize();
  const sticky = mode === 'phone' || mode === 'tablet';
  // Phone landscape has little height: the card may take at most half the viewport
  const cardHeight = mode === 'phoneLandscape' ? Math.floor(viewportHeight * 0.5) - 16 : PREVIEW_HEIGHT;
  const sheetWidth = mode === 'phone' ? viewportWidth : SHEET_WIDTH[mode];
  // Shrinks the whole sheet, up to half size, until it fits above the card's top edge
  const scale = Math.min(0.5, (cardHeight - 8) / sheetHeight(settings.displaySheetModules));

  return (
    <Box aria-hidden="true" sx={{ position: sticky ? 'sticky' : 'static', top: 0, zIndex: 1, mb: 2, bgcolor: 'background.paper' }}>
      <Box
        sx={{
          position: 'relative',
          overflow: 'hidden',
          boxSizing: 'border-box',
          height: cardHeight,
          p: 2,
          borderRadius: 2,
          border: 1,
          borderColor: 'divider',
          bgcolor: settings.backgroundColor ?? theme.palette.background.paper,
          color: settings.fontColor ?? theme.palette.text.primary,
        }}
      >
        <Typography
          component="p"
          sx={{
            fontFamily: settings.fontFamily ?? undefined,
            fontSize: settings.fontSize,
            lineHeight: settings.lineSpacing,
            textAlign: settings.textAlign,
            textIndent: paragraphIndentFor(settings.paragraphIndent),
            color: 'inherit',
          }}
        >
          {t('readerDisplay.preview.sample')}
        </Typography>

        <Box
          inert
          sx={{
            position: 'absolute',
            bottom: 0,
            left: '50%',
            width: sheetWidth,
            boxSizing: 'border-box',
            p: `${SHEET_PADDING}px`,
            borderRadius: 2,
            bgcolor: 'background.paper',
            color: 'text.primary',
            boxShadow: 2,
            transform: `translateX(-50%) scale(${scale})`,
            transformOrigin: 'bottom center',
          }}
        >
          <Typography
            variant="subtitle1"
            component="p"
            noWrap
            sx={{ height: SHEET_HEADER_HEIGHT, lineHeight: `${SHEET_HEADER_HEIGHT}px`, fontWeight: 600 }}
          >
            {t('readerDisplay.title')}
          </Typography>
          <DisplayModuleGrid modules={settings.displaySheetModules} />
        </Box>
      </Box>
    </Box>
  );
};

export default SheetPreview;
