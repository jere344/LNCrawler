import React from 'react';
import { Typography } from '@mui/material';
import { ReaderSettings } from '../ReaderSettings';
import { ChapterContent } from '@models/novels_types';

interface ReaderContentProps {
  chapter: ChapterContent;
  settings: ReaderSettings;
}

const bodyStyles = `
<style>
  #reader-content img { 
    max-width: 100%; 
    height: auto; 
  }
  #reader-content a {
    pointer-events: none;
    cursor: default;
    color: inherit;
  }
  #reader-content a:hover {
    text-decoration: none;
  }
  #reader-content code {
    padding: 0px 4px;
    font-family: monospace;
    font-size: 90%;
  }
  #reader-content form {
    display: none;
  }
  #reader-content.paragraph-indent p {
    text-indent: 2em;
  }
  #reader-content.paragraph-indent p:first-child,
  #reader-content.paragraph-indent p:first-of-type {
    text-indent: 0;
  }
</style>
` 

// Compare previous and new props to determine if re-render is needed
const arePropsEqual = (prevProps: ReaderContentProps, nextProps: ReaderContentProps) => {
  // Compare chapter properties that affect rendering
  const chapterChanged = 
    prevProps.chapter.body !== nextProps.chapter.body ||
    prevProps.chapter.images_path !== nextProps.chapter.images_path;
  
  // Compare settings properties that affect rendering
  const settingsChanged = 
    prevProps.settings.fontSize !== nextProps.settings.fontSize ||
    prevProps.settings.lineSpacing !== nextProps.settings.lineSpacing ||
    prevProps.settings.wordSpacing !== nextProps.settings.wordSpacing ||
    prevProps.settings.letterSpacing !== nextProps.settings.letterSpacing ||
    prevProps.settings.textAlign !== nextProps.settings.textAlign ||
    prevProps.settings.fontFamily !== nextProps.settings.fontFamily ||
    prevProps.settings.textSelectable !== nextProps.settings.textSelectable ||
    prevProps.settings.paragraphIndent !== nextProps.settings.paragraphIndent ||
    prevProps.settings.paragraphSpacing !== nextProps.settings.paragraphSpacing;
  
  // Only re-render if something important changed
  return !(chapterChanged || settingsChanged);
};

const ReaderContent: React.FC<ReaderContentProps> = ({ chapter, settings }) => {
  return (
    <Typography 
      sx={{ 
        fontSize: `${settings.fontSize}px`, 
        lineHeight: settings.lineSpacing,
        wordSpacing: `${settings.wordSpacing}px`,
        letterSpacing: `${settings.letterSpacing}px`,
        textAlign: settings.textAlign,
        fontFamily: settings.fontFamily || undefined,
        userSelect: settings.textSelectable ? 'text' : 'none',
        WebkitUserSelect: settings.textSelectable ? 'text' : 'none',
        MozUserSelect: settings.textSelectable ? 'text' : 'none',
        msUserSelect: settings.textSelectable ? 'text' : 'none',
        '& p': {
          marginBottom: `${settings.paragraphSpacing}em`,
        },
      }}
      id="reader-content"
      className={settings.paragraphIndent ? 'paragraph-indent' : ''}
      dangerouslySetInnerHTML= {{ __html: bodyStyles + chapter.body.replace(/src=\"images\//g, `src="${chapter.images_path}/`) }}
    />
  );
};

export default React.memo(ReaderContent, arePropsEqual);
