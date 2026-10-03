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
  BoldItalicUnderlineToggles, 
  UndoRedo, 
  BlockTypeSelect,
  ListsToggle,
  toolbarPlugin,
} from '@mdxeditor/editor';
import '@mdxeditor/editor/style.css';
import { createMDXEditorStyles } from '@utils/mdxEditorStyles';
import { useTranslation } from 'react-i18next';

interface EditableMDXEditorProps {
  content: string;
  onChange: (content: string) => void;
  placeholder?: string;
  editorKey?: number;
}

const EditableMDXEditor: React.FC<EditableMDXEditorProps> = ({ 
  content, 
  onChange, 
  placeholder,
  editorKey = 0
}) => {
  const theme = useTheme();
  const { t } = useTranslation();
  const editorStyles = createMDXEditorStyles(theme, false);

  return (
    <Box 
      sx={{ 
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 1,
        overflow: 'hidden',
        ...editorStyles
      }}
    >
      <MDXEditor
        key={editorKey}
        markdown={content}
        onChange={onChange}
        plugins={[
          headingsPlugin(),
          listsPlugin(),
          quotePlugin(),
          thematicBreakPlugin(),
          markdownShortcutPlugin(),
          toolbarPlugin({
            toolbarContents: () => (
              <Box sx={{ 
                  display: 'flex', 
                  gap: 1,
                  alignItems: 'center',
              }}>
                <UndoRedo />
                <BlockTypeSelect />
                <BoldItalicUnderlineToggles />
                <ListsToggle />
              </Box>
            )
          })
        ]}
        placeholder={placeholder ?? t('reviewForm.startWriting')}
      />
    </Box>
  );
};

export default EditableMDXEditor;
