import { describe, it, expect } from 'vitest';
import { parseReaderSettingsFile } from './readerSettingsBackup';
import { defaultSettings } from './readerDefaults';

describe('parseReaderSettingsFile', () => {
  it('maps an old 1.0 file with centerTapToOpenSettings:false to a single tap that does nothing', () => {
    const text = JSON.stringify({ version: '1.0', centerTapToOpenSettings: false, fontSize: 20 });

    const settings = parseReaderSettingsFile(text);
    expect(settings.centerSingleTap).toBe('none');
    expect(settings.fontSize).toBe(20);
  });

  it('falls back to the defaults for bad values', () => {
    const text = JSON.stringify({ fontSize: 99, controlsTrigger: 'tripleTap', textAlign: 'diagonal' });

    expect(parseReaderSettingsFile(text)).toEqual(defaultSettings);
  });

  it('reads a backup with the old narrated engine as the audiobook preference', () => {
    const text = JSON.stringify({ version: '2.0', ttsEngine: 'narrated', fontSize: 20 });

    const settings = parseReaderSettingsFile(text);
    expect(settings.ttsPreferAudiobook).toBe(true);
    expect(settings.ttsEngine).toBe('browser');
    expect(settings.fontSize).toBe(20);
  });

  it('throws when the JSON is an array', () => {
    expect(() => parseReaderSettingsFile('[1, 2]')).toThrow();
  });

  it('throws when the JSON is invalid', () => {
    expect(() => parseReaderSettingsFile('{not json')).toThrow();
  });
});
