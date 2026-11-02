import { defaultSettings } from './readerDefaults';
import { sanitizeSettings, type ReaderSettings } from './readerSettingsSchema';

// Downloads the settings as a JSON file
export const exportReaderSettings = (settings: ReaderSettings): void => {
  const settingsData = {
    ...settings,
    exportDate: new Date().toISOString(),
    version: '2.0'
  };

  const blob = new Blob([JSON.stringify(settingsData, null, 2)], {
    type: 'application/json'
  });

  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `lncrawler-reader-settings-${new Date().toISOString().split('T')[0]}.json`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

// Throws on invalid JSON. Old 1.0 files are read the same way.
export const parseReaderSettingsFile = (text: string): ReaderSettings => {
  const parsed: unknown = JSON.parse(text);
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Settings file must contain a JSON object');
  }
  return { ...defaultSettings, ...sanitizeSettings(parsed) };
};

// Asks for a JSON file. Resolves with its text, or null when no file was chosen.
export const pickJsonFile = (): Promise<string | null> =>
  new Promise((resolve, reject) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';

    input.onchange = (event) => {
      const file = (event.target as HTMLInputElement).files?.[0];
      if (!file) {
        resolve(null);
        return;
      }

      const reader = new FileReader();
      reader.onload = (e) => resolve(e.target?.result as string);
      reader.onerror = () => reject(reader.error);
      reader.readAsText(file);
    };

    input.click();
  });
