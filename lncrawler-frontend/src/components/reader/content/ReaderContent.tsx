import React from 'react';
import DOMPurify from 'dompurify';
import { Typography } from '@mui/material';
import { ReaderSettings } from '../readerSettingsSchema';
import { ChapterContent } from '@models/novels_types';
import { PARAGRAPH_INDENT, readerTextStyles } from './readerTextStyles';

interface ReaderContentProps {
  chapter: ChapterContent;
  settings: ReaderSettings;
  // id of the text element, so TTS can find it
  contentId: string;
}

const bodyStyles = `
<style>
  .reader-content img { 
    max-width: 100%; 
    height: auto; 
    break-inside: avoid;
  }
  .reader-content figure,
  .reader-content table,
  .reader-content pre {
    break-inside: avoid;
  }
  .reader-content h1,
  .reader-content h2,
  .reader-content h3 {
    break-after: avoid;
  }
  .reader-content a {
    pointer-events: none;
    cursor: default;
    color: inherit;
  }
  .reader-content a:hover {
    text-decoration: none;
  }
  .reader-content code {
    padding: 0px 4px;
    font-family: monospace;
    font-size: 90%;
  }
  .reader-content form {
    display: none;
  }
  .reader-content.paragraph-indent p {
    text-indent: ${PARAGRAPH_INDENT};
  }
  .reader-content.paragraph-indent p:first-child,
  .reader-content.paragraph-indent p:first-of-type {
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
  
  // A different id is a different section of the stream
  const idChanged = prevProps.contentId !== nextProps.contentId;

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
  return !(chapterChanged || idChanged || settingsChanged);
};

const ReaderContent: React.FC<ReaderContentProps> = ({ chapter, settings, contentId }) => {
  const safeBody = React.useMemo(() => {
    const withImages = (chapter.body || '').replace(
      /src="images\//g,
      `src="${chapter.images_path || ''}/`
    );
    return DOMPurify.sanitize(withImages, { USE_PROFILES: { html: true } });
  }, [chapter.body, chapter.images_path]);

  return (
    <Typography
      sx={readerTextStyles(settings)}
      id={contentId}
      className={settings.paragraphIndent ? 'reader-content paragraph-indent' : 'reader-content'}
      dangerouslySetInnerHTML= {{ __html: bodyStyles + safeBody }}
    />
  );
};

export default React.memo(ReaderContent, arePropsEqual);
