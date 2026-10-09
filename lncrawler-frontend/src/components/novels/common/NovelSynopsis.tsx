import React from 'react';
import DOMPurify from 'dompurify';
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
          '& img': { maxWidth: '100%', height: 'auto' },
        }} 
        dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(synopsis, { USE_PROFILES: { html: true } }) }} 
      />
    </Box>
  );
};

export default NovelSynopsis;
