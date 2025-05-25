import React, { ReactNode } from 'react';
import { Typography, Paper, Box, useTheme, alpha } from '@mui/material';

interface SectionContainerProps {
  title: string;
  icon: React.ReactNode;
  children: ReactNode;
}

const SectionContainer: React.FC<SectionContainerProps> = ({ title, icon, children }) => {
  const theme = useTheme();
  
  return (
    <Paper 
      elevation={3} 
      sx={{ 
        p: 3, 
        mb: 4, 
        borderRadius: 3,
        background: theme.palette.mode === 'dark' 
          ? `linear-gradient(135deg, ${alpha(theme.palette.background.paper, 0.9)} 0%, ${alpha(theme.palette.background.paper, 1)} 100%)`
          : theme.palette.background.paper,
        position: 'relative',
      }}
    >
      {/* Decorative element */}
      <Box
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '5px',
          height: '100%',
          background: `linear-gradient(to bottom, ${theme.palette.primary.main}, ${theme.palette.secondary.main})`,
        }}
      />
      
      <Typography 
        variant="h5" 
        gutterBottom 
        sx={{ 
          pl: 2,
          borderBottom: `1px solid ${alpha(theme.palette.divider, 0.1)}`,
          pb: 1,
          display: 'flex',
          alignItems: 'center',
        }}
      >
        {React.cloneElement(icon as React.ReactElement<any, any>, { sx: { mr: 1, color: theme.palette.primary.main } })}
        {title}
      </Typography>
      
      {children}
    </Paper>
  );
};

export default SectionContainer;
