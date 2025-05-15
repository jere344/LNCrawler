import React from 'react';
import { Typography, Paper, Box, useTheme, alpha } from '@mui/material';
import BookmarkIcon from '@mui/icons-material/Bookmark';

interface NovelSynopsisProps {
  synopsis: string;
}

const NovelSynopsis: React.FC<NovelSynopsisProps> = ({ synopsis }) => {
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
        overflow: 'hidden',
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
        <BookmarkIcon sx={{ mr: 1, color: theme.palette.primary.main }} />
        Synopsis
      </Typography>
      
      <Box sx={{ px: 2, py: 1 }}>
        <Typography 
          variant="body1" 
          sx={{ 
            lineHeight: 1.8,
            textAlign: 'justify',
            '& p': { mb: 1.5 },
          }} 
          dangerouslySetInnerHTML={{ __html: synopsis }} 
        />
      </Box>
    </Paper>
  );
};

export default NovelSynopsis;
