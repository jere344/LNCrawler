import { IconButton, Tooltip } from '@mui/material';
import FullscreenIcon from '@mui/icons-material/Fullscreen';
import FullscreenExitIcon from '@mui/icons-material/FullscreenExit';

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
