import type { ReaderLayoutMode } from '../hooks/useReaderLayout';
import type { ReaderPanel } from '../hooks/useReaderPanels';
import type { SettingsPageId } from '../settings/settingsPages';
import DisplaySheet from '../display/DisplaySheet';
import AllSettingsPanel from '../settings/AllSettingsPanel';

interface ReaderPanelsProps {
  panel: ReaderPanel;
  mode: ReaderLayoutMode;
  bottomOffset: number;
  settingsPage?: SettingsPageId;
  novelLanguage: string;
  hasNarration: boolean;
  onTtsBeforePreview?: () => void;
  onClosePanel: () => void;
  onOpenCustomize: () => void;
  onCloseCustomize: () => void;
  onOpenAllSettings: () => void;
}

// The panels that open over the reader, one at a time, chosen by the panel state
const ReaderPanels = ({
  panel,
  mode,
  bottomOffset,
  settingsPage,
  novelLanguage,
  hasNarration,
  onTtsBeforePreview,
  onClosePanel,
  onOpenCustomize,
  onCloseCustomize,
  onOpenAllSettings,
}: ReaderPanelsProps) => (
  <>
    {panel === 'display' && (
      <DisplaySheet
        mode={mode}
        bottomOffset={bottomOffset}
        onClose={onClosePanel}
        onCustomize={onOpenCustomize}
        onAllSettings={onOpenAllSettings}
      />
    )}

    {/* Keyed on the page, so a new page (from the TTS tune button) opens while the panel is already up */}
    {panel === 'settings' && (
      <AllSettingsPanel
        key={settingsPage ?? 'home'}
        mode={mode}
        initialPage={settingsPage}
        novelLanguage={novelLanguage}
        hasNarration={hasNarration}
        onBeforePreview={onTtsBeforePreview}
        onBack={onClosePanel}
        onClose={onClosePanel}
      />
    )}

    {/* Customize opens the customizer page of the settings panel; back returns to the display sheet */}
    {panel === 'customize' && (
      <AllSettingsPanel
        mode={mode}
        initialPage="custom"
        novelLanguage={novelLanguage}
        hasNarration={hasNarration}
        onBeforePreview={onTtsBeforePreview}
        onBack={onCloseCustomize}
        onClose={onClosePanel}
      />
    )}
  </>
);

export default ReaderPanels;
