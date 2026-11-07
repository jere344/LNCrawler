import { AppBar, Box, Button, Slide, Toolbar, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { ChapterStepButton } from './ChapterStepButtons';
import ChapterProgress from './ChapterProgress';
import type { ReaderBarProps } from './readerBarTypes';
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion';
import { useBarActions } from './barActions';

interface ReaderBottomBarProps extends ReaderBarProps {
  bottomOffset: number;
  // The TTS bar is open; on narrow screens the action row is hidden to save height
  ttsOpen: boolean;
  isNarrow: boolean;
  // Phone landscape: with a side panel or the sheet open, the action row is hidden as the screen is too short for it
  isPhoneLandscape: boolean;
}

// Touch layouts: slides up from the bottom, above the TTS bar when that is open
const ReaderBottomBar = ({
  controlsVisible,
  hasPrev,
  hasNext,
  displayOpen,
  commentsOpen,
  commentCount,
  reservedStart,
  reservedEnd,
  shortcuts,
  onPrevious,
  onNext,
  onDisplay,
  onListen,
  onComments,
  onSettings,
  bottomOffset,
  ttsOpen,
  isNarrow,
  isPhoneLandscape,
}: ReaderBottomBarProps) => {
  const theme = useTheme();
  const reducedMotion = usePrefersReducedMotion();

  const actions = useBarActions({ displayOpen, commentsOpen, commentCount, shortcuts, onDisplay, onListen, onComments, onSettings });

  return (
    <Slide direction="up" in={controlsVisible} timeout={reducedMotion ? 0 : undefined} mountOnEnter unmountOnExit>
      <AppBar
        position="fixed"
        color="inherit"
        elevation={4}
        data-reader-surface
        sx={{
          top: 'auto',
          bottom: bottomOffset,
          insetInlineStart: reservedStart,
          insetInlineEnd: reservedEnd,
          width: 'auto',
          zIndex: theme.zIndex.appBar + 1,
          bgcolor: 'background.paper',
          color: 'text.primary',
          borderTop: `1px solid ${theme.palette.divider}`,
          backdropFilter: 'blur(8px)',
          paddingBottom: bottomOffset === 0 ? 'env(safe-area-inset-bottom)' : 0,
        }}
      >
        <Toolbar sx={{ flexDirection: 'column', alignItems: 'stretch', gap: 0.5, py: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <ChapterStepButton direction="prev" enabled={hasPrev} onClick={onPrevious} shortcut={shortcuts.prev} />
            <ChapterProgress />
            <ChapterStepButton direction="next" enabled={hasNext} onClick={onNext} shortcut={shortcuts.next} />
          </Box>

          {!(ttsOpen && isNarrow) && !(isPhoneLandscape && reservedEnd > 0) && (
            <Box sx={{ display: 'flex', justifyContent: 'space-around' }}>
              {actions.map((action) => (
                <Button
                  key={action.label}
                  onClick={action.onClick}
                  aria-label={action.ariaLabel}
                  aria-expanded={action.expanded}
                  aria-keyshortcuts={action.keyShortcut}
                  color="inherit"
                  sx={{ flexDirection: 'column', gap: 0.25, minWidth: 0, flex: 1, color: 'text.secondary' }}
                >
                  {action.icon}
                  <Typography variant="caption" component="span">{action.label}</Typography>
                </Button>
              ))}
            </Box>
          )}
        </Toolbar>
      </AppBar>
    </Slide>
  );
};

export default ReaderBottomBar;
