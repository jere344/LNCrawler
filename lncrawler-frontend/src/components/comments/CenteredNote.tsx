import type { ReactNode } from 'react';
import { Box, Typography } from '@mui/material';

interface CenteredNoteProps {
  // Shows the message as an error
  error?: boolean;
  // Shown under the message, e.g. a retry button
  action?: ReactNode;
  children: ReactNode;
}

// A message in place of the comments: a failure, an empty list, or the end of it
const CenteredNote = ({ error = false, action, children }: CenteredNoteProps) => (
  <Box sx={{ py: 3, textAlign: 'center' }}>
    <Typography sx={{ color: error ? 'error.main' : 'text.secondary' }}>{children}</Typography>
    {action}
  </Box>
);

export default CenteredNote;
