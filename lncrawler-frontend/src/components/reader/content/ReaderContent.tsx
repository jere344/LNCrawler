import React from 'react';
import { Typography } from '@mui/material';
import { ReaderSettings } from '../ReaderSettings';

interface ReaderContentProps {
  content: string;
  settings: ReaderSettings;
}

const ReaderContent: React.FC<ReaderContentProps> = ({ content, settings }) => {
  return (
    <Typography 
      sx={{ 
        fontSize: `${settings.fontSize}px`, 
        lineHeight: settings.lineSpacing,
        textAlign: settings.textAlign,
        fontFamily: settings.fontFamily || undefined,
        userSelect: settings.textSelectable ? 'text' : 'none',
        WebkitUserSelect: settings.textSelectable ? 'text' : 'none',
        MozUserSelect: settings.textSelectable ? 'text' : 'none',
        msUserSelect: settings.textSelectable ? 'text' : 'none',
      }}
      dangerouslySetInnerHTML={{ __html: content }}
    />
  );
};

export default ReaderContent;
