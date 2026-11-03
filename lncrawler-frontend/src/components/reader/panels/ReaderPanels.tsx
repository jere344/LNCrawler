import type { ReaderLayoutMode } from '../hooks/useReaderLayout';
import type { ReaderPanel } from '../hooks/useReaderPanels';
import type { SettingsPageId } from '../settings/settingsPages';
import DisplaySheet from '../display/DisplaySheet';
import AllSettingsPanel from '../settings/AllSettingsPanel';
import ChapterListPanel, { type ChapterListPanelProps } from './ChapterListPanel';

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
  onTtsBeforePreview,
  onClosePanel,
  onBack,
  onPushPage,
  onSetDeskPage,
  onStartSearch,
  onOpenCustomize,
  onOpenAllSettings,
}: ReaderPanelsProps) => (
  <>
    {panel === 'chapters' && (
      <ChapterListPanel {...chapterList} mode={mode} onClose={onClosePanel} />
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

export default ReaderPanels;
