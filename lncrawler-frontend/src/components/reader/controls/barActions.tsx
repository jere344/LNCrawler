import type { ReactNode } from 'react';
import { Badge, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import CommentIcon from '@mui/icons-material/Comment';
import HeadphonesIcon from '@mui/icons-material/Headphones';
import SettingsIcon from '@mui/icons-material/Settings';
import type { ReaderBarProps } from './readerBarTypes';

// One action of a reader bar: the bottom bar captions it with `label`, the desktop toolbar uses it as the tooltip
export interface BarAction {
  label: string;
  // The accessible name when it is not the label (the comments count)
  ariaLabel?: string;
  icon: ReactNode;
  onClick: () => void;
  // Set on the actions that open a panel
  expanded?: boolean;
  keyShortcut?: string;
}

type BarActionProps = Pick<ReaderBarProps,
  'displayOpen' | 'commentsOpen' | 'commentCount' | 'shortcuts' | 'onDisplay' | 'onListen' | 'onComments' | 'onSettings'>;

// The display, listen, comments and settings actions, shared by the bottom bar and the desktop toolbar
export function useBarActions({
  displayOpen,
  commentsOpen,
  commentCount,
  shortcuts,
  onDisplay,
  onListen,
  onComments,
  onSettings,
}: BarActionProps): BarAction[] {
  const { t } = useTranslation();
  return [
    {
      label: t('readerControls.display'),
      icon: <Typography component="span" sx={{ fontWeight: 600, lineHeight: 1 }}>Aa</Typography>,
      onClick: onDisplay,
      expanded: displayOpen,
      keyShortcut: shortcuts.display,
    },
    { label: t('reader.listen'), icon: <HeadphonesIcon />, onClick: onListen },
    {
      label: t('readerControls.comments'),
      // The count is announced, the visible label stays short
      ariaLabel: t('readerControls.commentsCount', { count: commentCount }),
      icon: (
        <Badge badgeContent={commentCount} max={999} color="primary" invisible={commentCount === 0}>
          <CommentIcon />
        </Badge>
      ),
      onClick: onComments,
      expanded: commentsOpen,
      keyShortcut: shortcuts.comments,
    },
    { label: t('readerControls.settings'), icon: <SettingsIcon />, onClick: onSettings },
  ];
}
