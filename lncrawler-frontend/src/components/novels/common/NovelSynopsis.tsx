import React from 'react';
import { Typography, Box } from '@mui/material';

interface NovelSynopsisProps {
  synopsis: string;
}

const NovelSynopsis: React.FC<NovelSynopsisProps> = ({ synopsis }) => {
  return (
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
  );
};

export default NovelSynopsis;
