import { AppBar, Badge, Box, ButtonBase, Divider, IconButton, type IconButtonProps, Toolbar, Tooltip, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ListIcon from '@mui/icons-material/List';
import BookmarkAddIcon from '@mui/icons-material/BookmarkAdd';
import DoneIcon from '@mui/icons-material/Done';
import HeadphonesIcon from '@mui/icons-material/Headphones';
import CommentIcon from '@mui/icons-material/Comment';
import SettingsIcon from '@mui/icons-material/Settings';
import FullscreenIcon from '@mui/icons-material/Fullscreen';
import FullscreenExitIcon from '@mui/icons-material/FullscreenExit';
import DirectionalIcon from '../DirectionalIcon';
import { ChapterStepButton } from './ChapterStepButtons';
import ChapterProgress from './ChapterProgress';
import type { ReaderBarProps } from './readerBarTypes';
import { reservedMargin } from '../panels/panelLayout';

// Height of the MUI Toolbar at sm and up (the desktop layout)
const TOOLBAR_HEIGHT = 64;

interface ToolbarActionProps extends Omit<IconButtonProps, 'aria-label'> {
  label: string;
}

// An icon button whose label is both its tooltip and its accessible name. A title sets a different tooltip.
const ToolbarAction = ({ label, title = label, children, ...buttonProps }: ToolbarActionProps) => (
  <Tooltip title={title}>
    <IconButton color="inherit" aria-label={label} {...buttonProps}>
      {children}
    </IconButton>
  </Tooltip>
);

// Desktop: one sticky bar at the top that slides out of the way when the controls are hidden
const ReaderDesktopToolbar = ({
  controlsVisible,
  chapterTitle,
  novelTitle,
  hasPrev,
  hasNext,
  displayOpen,
  commentsOpen,
  commentCount,
  reservedStart,
  reservedEnd,
  shortcuts,
  markRead: { showMarkRead, markReadSuccess, markingAsRead, onMarkAsRead },
  fullscreen,
  fullscreenLabel,
  fullscreenTitle,
  onHome,
  onChapterList,
  onPrevious,
  onNext,
  onDisplay,
  onListen,
  onComments,
  onSettings,
}: ReaderBarProps) => {
  const { t } = useTranslation();
  const displayLabel = t('readerControls.display');
  const commentsLabel = t('readerControls.comments');

  // Hidden: slid above the viewport, out of the tab order, and no longer taking up space
  return (
    <AppBar
      position="sticky"
      color="inherit"
      elevation={1}
      data-reader-surface
      sx={{
        top: 0,
        // Auto width, so the end margin narrows the bar and the open panel does not cover its buttons
        width: 'auto',
        bgcolor: 'background.paper',
        color: 'text.primary',
        marginInlineStart: reservedMargin(reservedStart),
        marginInlineEnd: reservedMargin(reservedEnd),
        transform: controlsVisible ? 'none' : 'translateY(-100%)',
        marginBottom: controlsVisible ? 0 : `-${TOOLBAR_HEIGHT}px`,
        visibility: controlsVisible ? 'visible' : 'hidden',
        transition: 'transform 0.2s ease, visibility 0.2s, margin 0.25s ease-out',
        '@media (prefers-reduced-motion: reduce)': { transition: 'none' },
      }}
    >
      <Toolbar sx={{ gap: 1 }}>
        <ToolbarAction label={t('readerControls.backToNovel')} onClick={onHome}>
          <DirectionalIcon><ArrowBackIcon /></DirectionalIcon>
        </ToolbarAction>
        <ToolbarAction label={t('readerControls.chapterNavigation')} onClick={onChapterList}>
          <ListIcon />
        </ToolbarAction>

        <ButtonBase
          onClick={onChapterList}
          aria-label={t('readerChapters.open')}
          sx={{ minWidth: 0, flexShrink: 1, justifyContent: 'flex-start', textAlign: 'start', borderRadius: 1, py: 0.5 }}
        >
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h6" noWrap sx={{ fontSize: '1.1rem' }}>
              {chapterTitle}
            </Typography>
            <Typography variant="caption" component="p" color="text.secondary" noWrap>
              {novelTitle}
            </Typography>
          </Box>
        </ButtonBase>

        {/* Never narrower than its two buttons, so the title shrinks first */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1, minWidth: 'min-content' }}>
          <ChapterStepButton direction="prev" enabled={hasPrev} onClick={onPrevious} shortcut={shortcuts.prev} />
          <ChapterProgress />
          <ChapterStepButton direction="next" enabled={hasNext} onClick={onNext} shortcut={shortcuts.next} />
        </Box>

        <Divider orientation="vertical" flexItem />

        <ToolbarAction
          label={displayLabel}
          title={shortcuts.display ? `${displayLabel} (${shortcuts.display})` : displayLabel}
          onClick={onDisplay}
          aria-expanded={displayOpen}
          aria-keyshortcuts={shortcuts.display}
        >
          <Typography component="span" sx={{ fontWeight: 600, lineHeight: 1 }}>Aa</Typography>
        </ToolbarAction>
        <ToolbarAction label={t('reader.listen')} onClick={onListen}>
          <HeadphonesIcon />
        </ToolbarAction>
        <ToolbarAction
          label={t('readerControls.commentsCount', { count: commentCount })}
          title={shortcuts.comments ? `${commentsLabel} (${shortcuts.comments})` : commentsLabel}
          onClick={onComments}
          aria-expanded={commentsOpen}
          aria-keyshortcuts={shortcuts.comments}
        >
          <Badge badgeContent={commentCount} max={999} color="primary" invisible={commentCount === 0}>
            <CommentIcon />
          </Badge>
        </ToolbarAction>
        <ToolbarAction label={t('readerControls.settings')} onClick={onSettings}>
          <SettingsIcon />
        </ToolbarAction>

        {showMarkRead && (
          <Tooltip title={t('markAsRead.tooltip')}>
            <span>
              <IconButton
                color="primary"
                onClick={onMarkAsRead}
                disabled={markingAsRead || markReadSuccess}
                aria-label={markReadSuccess ? t('readerControls.markedAsRead') : t('readerControls.markAsRead')}
              >
                {markReadSuccess ? <DoneIcon /> : <BookmarkAddIcon />}
              </IconButton>
            </span>
          </Tooltip>
        )}
        {fullscreen.supported && (
          <ToolbarAction
            label={fullscreenLabel}
            title={fullscreenTitle}
            onClick={fullscreen.onToggle}
            aria-pressed={fullscreen.active}
          >
            {fullscreen.active ? <FullscreenExitIcon /> : <FullscreenIcon />}
          </ToolbarAction>
        )}
      </Toolbar>
    </AppBar>
  );
};

export default ReaderDesktopToolbar;
