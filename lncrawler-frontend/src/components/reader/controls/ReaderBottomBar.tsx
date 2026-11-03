import { AppBar, Box, Button, Slide, Toolbar, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useTranslation } from 'react-i18next';
import CommentIcon from '@mui/icons-material/Comment';
import HeadphonesIcon from '@mui/icons-material/Headphones';
import SettingsIcon from '@mui/icons-material/Settings';
import { ChapterStepButton } from './ChapterStepButtons';
import ChapterProgress from './ChapterProgress';
import type { ReaderBarProps } from './readerBarTypes';
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion';

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
  const { t } = useTranslation();
  const theme = useTheme();
  const reducedMotion = usePrefersReducedMotion();

  const actions = [
    {
      label: t('readerControls.display'),
      icon: <Typography component="span" sx={{ fontWeight: 600, lineHeight: 1 }}>Aa</Typography>,
      onClick: onDisplay,
      expanded: displayOpen,
      keyShortcut: shortcuts.display,
    },
    { label: t('reader.listen'), icon: <HeadphonesIcon />, onClick: onListen },
    { label: t('readerControls.comments'), icon: <CommentIcon />, onClick: onComments },
    { label: t('readerControls.settings'), icon: <SettingsIcon />, onClick: onSettings },
  ];

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
