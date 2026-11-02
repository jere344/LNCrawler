import TtsSettings from '../TtsSettings';
import type { TtsPrefs } from '../../tts/ttsTypes';
import type { ReaderSettings } from '../../readerSettingsSchema';
import { updateReaderSetting } from '../../readerSettingsStore';
import { useReaderSettings } from '../../hooks/useReaderSettings';
import { useSettingsContext } from '../settingsContext';

const ListeningPage = () => {
  const settings = useReaderSettings();
  const { novelLanguage, onBeforePreview, hasNarration } = useSettingsContext();

  return (
    <TtsSettings
      prefs={settings}
      onChange={<K extends keyof TtsPrefs>(key: K, value: TtsPrefs[K]) =>
        updateReaderSetting(key, value as ReaderSettings[K])}
      novelLanguage={novelLanguage}
      onBeforePreview={onBeforePreview}
      hasNarration={hasNarration}
    />
  );
};

export default ListeningPage;
