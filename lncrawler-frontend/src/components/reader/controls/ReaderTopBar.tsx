import { AppBar, Box, ButtonBase, IconButton, Slide, Toolbar, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useTranslation } from 'react-i18next';
import HomeIcon from '@mui/icons-material/Home';
import ListIcon from '@mui/icons-material/List';
import type { ReaderBarProps } from './readerBarTypes';
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion';
import { FullscreenButton, MarkReadButton } from './BarButtons';

// Touch layouts: slides in from the top when the bars are shown
const ReaderTopBar = ({
  controlsVisible,
  chapterTitle,
  novelTitle,
  reservedStart,
  reservedEnd,
  markRead: { showMarkRead, markReadSuccess, markingAsRead, onMarkAsRead },
  fullscreen,
  fullscreenLabel,
  fullscreenTitle,
  onHome,
  onChapterList,
}: ReaderBarProps) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const reducedMotion = usePrefersReducedMotion();

  return (
    <Slide direction="down" in={controlsVisible} timeout={reducedMotion ? 0 : undefined} mountOnEnter unmountOnExit>
      <AppBar
        position="fixed"
        color="inherit"
        elevation={4}
        data-reader-surface
        sx={{
          top: 0,
          insetInlineStart: reservedStart,
          insetInlineEnd: reservedEnd,
          width: 'auto',
          zIndex: theme.zIndex.appBar + 1,
          bgcolor: 'background.paper',
          color: 'text.primary',
          borderBottom: `1px solid ${theme.palette.divider}`,
          backdropFilter: 'blur(8px)',
          paddingTop: 'env(safe-area-inset-top)',
        }}
      >
        <Toolbar sx={{ height: 64, minHeight: 64, gap: 1 }}>
          <IconButton edge="start" color="inherit" onClick={onChapterList} aria-label={t('readerControls.chapterNavigation')}>
            <ListIcon />
          </IconButton>

          <IconButton color="inherit" onClick={onHome} aria-label={t('readerControls.backToNovel')}>
            <HomeIcon />
          </IconButton>

          <ButtonBase
            onClick={onHome}
            aria-label={t('readerControls.backToNovel')}
            sx={{ flex: 1, minWidth: 0, justifyContent: 'flex-start', textAlign: 'start', borderRadius: 1, py: 0.5 }}
          >
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="subtitle1" noWrap sx={{ fontWeight: 'medium', lineHeight: 1.3 }}>
                {chapterTitle}
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap component="div">
                {novelTitle}
              </Typography>
            </Box>
          </ButtonBase>

          {showMarkRead && (
            <MarkReadButton markReadSuccess={markReadSuccess} markingAsRead={markingAsRead} onMarkAsRead={onMarkAsRead} />
          )}
          {fullscreen.supported && (
            <FullscreenButton active={fullscreen.active} label={fullscreenLabel} title={fullscreenTitle} onToggle={fullscreen.onToggle} />
          )}
        </Toolbar>
      </AppBar>
    </Slide>
  );
};

export default ReaderTopBar;
