import type { ReactNode } from 'react';
import { Box, useTheme } from '@mui/material';

// Icons that point forward (chevrons, back arrows) mirror under RTL, where forward is to the left
const DirectionalIcon = ({ children }: { children: ReactNode }) => {
  const theme = useTheme();
  return (
    <Box component="span" sx={{ display: 'inline-flex', transform: theme.direction === 'rtl' ? 'scaleX(-1)' : 'none' }}>
      {children}
    </Box>
  );
};

export default DirectionalIcon;
