import React from 'react';
import { Paper, Typography } from '@mui/material';
import type { SvgIconComponent } from '@mui/icons-material';

interface LoginRequiredPanelProps {
  icon: SvgIconComponent;
  title: string;
  description: string;
  hint?: string;
}

// Placeholder shown in place of a page that needs a logged-in user.
const LoginRequiredPanel: React.FC<LoginRequiredPanelProps> = ({ icon: Icon, title, description, hint }) => (
  <Paper
    elevation={3}
    sx={{
      p: 4,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 2,
      mx: 'auto',
      maxWidth: 'md',
      my: 4,
    }}
  >
    <Icon sx={{ fontSize: 60, color: 'primary.main', mb: 2 }} />
    <Typography variant="h5" component="h1" gutterBottom>
      {title}
    </Typography>
    <Typography variant="body1" align="center" sx={{ color: 'text.secondary' }}>
      {description}
    </Typography>
    {hint && (
      <Typography variant="body2" align="center" sx={{ color: 'text.secondary' }}>
        {hint}
      </Typography>
    )}
  </Paper>
);

export default LoginRequiredPanel;
