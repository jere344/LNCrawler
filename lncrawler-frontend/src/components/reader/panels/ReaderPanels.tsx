import { Box, Fade, Slide, useTheme } from '@mui/material';
import type { ReaderLayoutMode } from '../hooks/useReaderLayout';
import type { ReaderPanel } from '../hooks/useReaderPanels';
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion';
import type { SettingsPageId } from '../settings/settingsPages';
import DisplaySheet from '../display/DisplaySheet';
import AllSettingsPanel from '../settings/AllSettingsPanel';
import ChapterListPanel, { type ChapterListPanelProps } from './ChapterListPanel';
import CommentsPanel, { type CommentsPanelProps } from '../comments/CommentsPanel';

interface ReaderPanelsProps {
  panel: ReaderPanel;
  mode: ReaderLayoutMode;
  bottomOffset: number;
  pages: SettingsPageId[];
  searching: boolean;
  novelLanguage: string;
  hasNarration: boolean;
  chapterNumber: number;
  chapterList: Omit<ChapterListPanelProps, 'mode' | 'onClose'>;
  comments: Omit<CommentsPanelProps, 'mode' | 'onClose'>;
  onTtsBeforePreview?: () => void;
  onClosePanel: () => void;
  onBack: () => void;
  onPushPage: (page: SettingsPageId) => void;
  onSetDeskPage: (page: SettingsPageId | null) => void;
  onStartSearch: () => void;
  onOpenCustomize: () => void;
  onOpenAllSettings: () => void;
}

// The panels that open over the reader, one at a time, chosen by the panel state
const ReaderPanels = ({
  panel,
  mode,
  bottomOffset,
  pages,
  searching,
  novelLanguage,
  hasNarration,
  chapterNumber,
  chapterList,
  comments,
  onTtsBeforePreview,
  onClosePanel,
  onBack,
  onPushPage,
  onSetDeskPage,
  onStartSearch,
  onOpenCustomize,
  onOpenAllSettings,
}: ReaderPanelsProps) => {
  const theme = useTheme();
  // Transitions run at the MUI default length, or not at all when the system asks for less motion
  const timeout = usePrefersReducedMotion() ? 0 : undefined;
  const chaptersOpen = panel === 'chapters';

  return (
    <>
      {/* Phones: the list and the comments overlay the text, and a tap on the rest of the screen closes them */}
      {mode === 'phone' && (
        <Fade in={chaptersOpen || panel === 'comments'} timeout={timeout} unmountOnExit>
          <Box
            aria-hidden
            onClick={onClosePanel}
            sx={{
              position: 'fixed',
              inset: 0,
              zIndex: theme.zIndex.appBar + 2,
              bgcolor: 'rgba(0, 0, 0, 0.4)',
            }}
          />
        </Fade>
      )}

      <Slide
        in={chaptersOpen}
        direction={theme.direction === 'rtl' ? 'left' : 'right'}
        timeout={timeout}
        appear
        mountOnEnter
        unmountOnExit
      >
        <ChapterListPanel {...chapterList} mode={mode} onClose={onClosePanel} />
      </Slide>

      {panel === 'comments' && (
        <CommentsPanel {...comments} mode={mode} bottomOffset={bottomOffset} onClose={onClosePanel} />
      )}

      {panel === 'display' && (
        <DisplaySheet
          mode={mode}
          bottomOffset={bottomOffset}
          onClose={onClosePanel}
          onCustomize={onOpenCustomize}
          onAllSettings={onOpenAllSettings}
        />
      )}

      {/* Customize is the customizer page of the settings panel; its back returns to the display sheet */}
      {(panel === 'settings' || panel === 'customize') && (
        <AllSettingsPanel
          mode={mode}
          pages={pages}
          searching={searching}
          novelLanguage={novelLanguage}
          hasNarration={hasNarration}
          chapterNumber={chapterNumber}
          onBeforePreview={onTtsBeforePreview}
          onBack={onBack}
          onPushPage={onPushPage}
          onSetDeskPage={onSetDeskPage}
          onStartSearch={onStartSearch}
          onClose={onClosePanel}
        />
      )}
    </>
  );
};

export default ReaderPanels;
