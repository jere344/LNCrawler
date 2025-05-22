import React from 'react';
import { Typography } from '@mui/material';
import { ReaderSettings } from '../ReaderSettings';
import { ChapterContent } from '@models/novels_types';

interface ReaderContentProps {
  chapter: ChapterContent;
  settings: ReaderSettings;
}

const ReaderContent: React.FC<ReaderContentProps> = ({ chapter, settings }) => {
  const imageStyles = `<style>img { max-width: 100%; height: auto; }</style>`;
  
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
      dangerouslySetInnerHTML= {{ __html: imageStyles + chapter.body.replace("src=\"images/", `src="${chapter.images_path}/`) }}
    />
  );
};

export default ReaderContent;
