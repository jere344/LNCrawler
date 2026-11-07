import { IconButton, Tooltip } from '@mui/material';
import { useTranslation } from 'react-i18next';
import BookmarkAddIcon from '@mui/icons-material/BookmarkAdd';
import DoneIcon from '@mui/icons-material/Done';
import FullscreenIcon from '@mui/icons-material/Fullscreen';
import FullscreenExitIcon from '@mui/icons-material/FullscreenExit';
import type { MarkReadProps } from './readerBarTypes';

// The mark-as-read button: a check once the chapter is marked, disabled while it is being marked
export const MarkReadButton = ({ markReadSuccess, markingAsRead, onMarkAsRead }: Omit<MarkReadProps, 'showMarkRead'>) => {
  const { t } = useTranslation();
  return (
    <IconButton
      color="primary"
      onClick={onMarkAsRead}
      disabled={markingAsRead || markReadSuccess}
      aria-label={markReadSuccess ? t('readerControls.markedAsRead') : t('readerControls.markAsRead')}
    >
      {markReadSuccess ? <DoneIcon /> : <BookmarkAddIcon />}
    </IconButton>
  );
};

// The fullscreen toggle, showing the state it would leave
export const FullscreenButton = ({ active, label, title, onToggle }: {
  active: boolean;
  label: string;
  title: string;
  onToggle: () => void;
}) => (
  <Tooltip title={title}>
    <IconButton color="inherit" onClick={onToggle} aria-label={label} aria-pressed={active}>
      {active ? <FullscreenExitIcon /> : <FullscreenIcon />}
    </IconButton>
  </Tooltip>
);
