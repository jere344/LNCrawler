import { AppBar, Box, IconButton, Slide, Toolbar, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useTranslation } from 'react-i18next';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ListIcon from '@mui/icons-material/List';
import BookmarkAddIcon from '@mui/icons-material/BookmarkAdd';
import DoneIcon from '@mui/icons-material/Done';
import type { ReaderBarProps } from './readerBarTypes';
import DirectionalIcon from '../DirectionalIcon';
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion';

// Touch layouts: slides in from the top when the bars are shown
const ReaderTopBar = ({
  controlsVisible,
  chapterTitle,
  novelTitle,
  reservedEnd,
  markRead: { showMarkRead, markReadSuccess, markingAsRead, onMarkAsRead },
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
          insetInlineStart: 0,
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
          <IconButton edge="start" color="inherit" onClick={onHome} aria-label={t('readerControls.backToNovel')}>
            <DirectionalIcon><ArrowBackIcon /></DirectionalIcon>
          </IconButton>

          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="subtitle1" noWrap sx={{ fontWeight: 'medium', lineHeight: 1.3 }}>
              {chapterTitle}
            </Typography>
            <Typography variant="caption" color="text.secondary" noWrap component="div">
              {novelTitle}
            </Typography>
          </Box>

          {showMarkRead && (
            <IconButton
              color="primary"
              onClick={onMarkAsRead}
              disabled={markingAsRead || markReadSuccess}
              aria-label={markReadSuccess ? t('readerControls.markedAsRead') : t('readerControls.markAsRead')}
            >
              {markReadSuccess ? <DoneIcon /> : <BookmarkAddIcon />}
            </IconButton>
          )}
          <IconButton color="inherit" onClick={onChapterList} aria-label={t('readerControls.chapterNavigation')}>
            <ListIcon />
          </IconButton>
        </Toolbar>
      </AppBar>
    </Slide>
  );
};

export default ReaderTopBar;
