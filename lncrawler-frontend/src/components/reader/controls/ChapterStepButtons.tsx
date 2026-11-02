import { IconButton, Tooltip } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import { useTranslation } from 'react-i18next';
import DirectionalIcon from '../DirectionalIcon';

interface ChapterStepButtonProps {
  direction: 'prev' | 'next';
  enabled: boolean;
  onClick: () => void;
  shortcut?: string;
}

// Previous and next chapter buttons, shared by the touch bottom bar and the desktop toolbar.
// Split so the progress indicator can sit between them: Prev, progress, Next.
export const ChapterStepButton = ({ direction, enabled, onClick, shortcut }: ChapterStepButtonProps) => {
  const { t } = useTranslation();
  const isPrev = direction === 'prev';
  const label = t(isPrev ? 'readerControls.previousChapter' : 'readerControls.nextChapter');

  return (
    <Tooltip title={label}>
      <span>
        <IconButton aria-label={label} aria-keyshortcuts={shortcut} disabled={!enabled} onClick={onClick}>
          <DirectionalIcon>{isPrev ? <ArrowBackIcon /> : <ArrowForwardIcon />}</DirectionalIcon>
        </IconButton>
      </span>
    </Tooltip>
  );
};
