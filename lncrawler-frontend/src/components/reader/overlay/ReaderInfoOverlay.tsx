import { Box, LinearProgress, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import BatteryChargingFullIcon from '@mui/icons-material/BatteryChargingFull';
import BatteryStdIcon from '@mui/icons-material/BatteryStd';
import type { OverlayItem, OverlayPosition, OverlaySize } from '../readerSettingsSchema';
import { useBattery, useBookPosition, useClock, useScrollProgress } from './useOverlayData';

interface ReaderInfoOverlayProps {
  items: OverlayItem[];
  position: OverlayPosition;
  size: OverlaySize;
  dimLevel: number;
  novelSlug: string;
  sourceSlug: string;
  chapterId: number;
  // Infinite mode: the section being read; null for the whole chapter
  sectionKey: string | null;
  // Space taken by side panels and by the TTS bar
  reservedStart: number;
  reservedEnd: number;
  bottomOffset: number;
  // Extra distance from the top or bottom edge, in px
  edgeOffset: number;
  // In fullscreen the browser reports a stale safe-area inset, which would leave a gap above the strip
  fullscreen: boolean;
}

const SIZE_SX = {
  full: { insetInlineStart: 0, insetInlineEnd: 0, borderRadius: 0 },
  center: { insetInlineStart: '50%', transform: 'translateX(-50%)', borderRadius: 4 },
  left: { insetInlineStart: 8, borderRadius: 4 },
  right: { insetInlineEnd: 8, borderRadius: 4 },
} as const;

// A small always-on strip of reading info. It never takes pointer events, so taps and swipes go through to the text.
const ReaderInfoOverlay = ({
  items, position, size, dimLevel, novelSlug, sourceSlug, chapterId, sectionKey, reservedStart, reservedEnd, bottomOffset, edgeOffset, fullscreen,
}: ReaderInfoOverlayProps) => {
  const { i18n, t } = useTranslation();
  const has = (item: OverlayItem) => items.includes(item);
  const now = useClock(has('time12') || has('time24'));
  const progress = useScrollProgress(has('chapterPage') || has('chapterSlider') || has('chapterPercent'), chapterId, sectionKey);
  const book = useBookPosition(has('bookPercent') || has('bookChapter'), novelSlug, sourceSlug, chapterId);
  const battery = useBattery(has('battery'));

  const renderItem = (item: OverlayItem) => {
    switch (item) {
      case 'time12':
        return now.toLocaleTimeString(i18n.language, { hour: 'numeric', minute: '2-digit', hour12: true });
      case 'time24':
        return now.toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit', hour12: false });
      case 'chapterPage':
        return t('readerOverlay.page', { page: progress.page, pages: progress.pages });
      case 'chapterSlider':
        return (
          <LinearProgress
            variant="determinate"
            value={progress.percent}
            aria-label={t('readerControls.readProgress')}
            sx={{ width: size === 'full' ? 120 : 64, height: 4, borderRadius: 2, bgcolor: 'action.disabledBackground' }}
          />
        );
      case 'chapterPercent':
        return `${progress.percent}%`;
      case 'battery':
        // Browsers without the Battery API show nothing
        return battery && (
          <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.25 }}>
            {battery.charging ? <BatteryChargingFullIcon sx={{ fontSize: 14 }} /> : <BatteryStdIcon sx={{ fontSize: 14 }} />}
            {battery.percent}%
          </Box>
        );
      case 'bookPercent':
        return book && `${Math.round((book.current / book.total) * 100)}%`;
      case 'bookChapter':
        return book && t('readerOverlay.chapterOf', { current: book.current, total: book.total });
      case 'dimness':
        return t('readerOverlay.dim', { percent: dimLevel });
    }
  };

  const cells = items
    .map((item) => ({ item, content: renderItem(item) }))
    .filter((cell) => cell.content);
  if (cells.length === 0) return null;

  // Full width sits flush on its edge; a pill floats a little inside it
  const gap = `${(size === 'full' ? 0 : 6) + edgeOffset}px`;
  const safeTop = fullscreen ? '0px' : 'env(safe-area-inset-top)';
  const safeBottom = fullscreen ? '0px' : 'env(safe-area-inset-bottom)';
  const edge = position === 'top'
    ? { top: `calc(${safeTop} + ${gap})` }
    : { bottom: bottomOffset === 0 ? `calc(${safeBottom} + ${gap})` : `calc(${bottomOffset}px + ${gap})` };
  const side = size === 'full' ? { insetInlineStart: reservedStart, insetInlineEnd: reservedEnd } : SIZE_SX[size];

  return (
    <Box
      aria-hidden
      data-reader-overlay
      sx={(theme) => ({
        position: 'fixed',
        zIndex: theme.zIndex.appBar - 1,
        pointerEvents: 'none',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 1.5,
        px: 1.5,
        py: 0.25,
        maxWidth: '100%',
        color: 'text.secondary',
        backgroundColor: 'background.default',
        opacity: 0.9,
        border: size === 'full' ? 0 : 1,
        borderColor: 'divider',
        ...edge,
        ...side,
      })}
    >
      {cells.map(({ item, content }) => (
        <Typography key={item} variant="caption" component="span" sx={{ fontVariantNumeric: 'tabular-nums', lineHeight: 1.4, whiteSpace: 'nowrap' }}>
          {content}
        </Typography>
      ))}
    </Box>
  );
};

export default ReaderInfoOverlay;
