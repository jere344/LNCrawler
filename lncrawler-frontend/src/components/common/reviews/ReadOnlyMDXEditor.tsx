import React from 'react';
import { Box } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { 
  MDXEditor, 
  headingsPlugin, 
  listsPlugin, 
  quotePlugin, 
  thematicBreakPlugin, 
  markdownShortcutPlugin,
} from '@mdxeditor/editor';
import '@mdxeditor/editor/style.css';
import { createMDXEditorStyles } from '@utils/mdxEditorStyles';

interface ReadOnlyMDXEditorProps {
  content: string;
  uniqueKey?: string;
}

const ReadOnlyMDXEditor: React.FC<ReadOnlyMDXEditorProps> = ({ content, uniqueKey }) => {
  const theme = useTheme();
  const editorStyles = createMDXEditorStyles(theme, true);

  return (
    <Box sx={{ mt: 1, ...editorStyles }}>
      <MDXEditor
        key={uniqueKey || `readonly-${content.substring(0, 50)}`}
        markdown={content}
        readOnly={true}
        plugins={[
          headingsPlugin(),
          listsPlugin(),
          quotePlugin(),
          thematicBreakPlugin(),
          markdownShortcutPlugin(),
        ]}
      />
    </Box>
  );
};

export default ReadOnlyMDXEditor;
