import { IconButton, Tooltip } from '@mui/material';
import FullscreenIcon from '@mui/icons-material/Fullscreen';
import FullscreenExitIcon from '@mui/icons-material/FullscreenExit';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';

// Opens the chapter's page on the source site in a new tab
export const SourceLinkButton = ({ href, label }: { href: string; label: string }) => (
  <Tooltip title={label}>
    <IconButton color="inherit" component="a" href={href} target="_blank" rel="noopener noreferrer" aria-label={label}>
      <OpenInNewIcon />
    </IconButton>
  </Tooltip>
);

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
