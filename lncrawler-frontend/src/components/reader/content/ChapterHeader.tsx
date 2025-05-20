import React from 'react';
import { Typography, Box } from '@mui/material';

interface ChapterHeaderProps {
  title: string;
  novelTitle: string;
  fontColor?: string | null;
}

const ChapterHeader: React.FC<ChapterHeaderProps> = ({ 
  title, 
  novelTitle,
  fontColor
}) => {
  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="h5" gutterBottom align="center" sx={{ color: fontColor || undefined }}>
        {title}
      </Typography>
      <Typography variant="subtitle1" sx={{ color: 'text.secondary', textAlign: 'center' }}>
        {novelTitle}
      </Typography>
    </Box>
  );
};

export default ChapterHeader;
