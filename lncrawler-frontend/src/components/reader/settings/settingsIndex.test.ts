import { describe, it, expect } from 'vitest';
import { defaultSettings } from '../readerDefaults';
import type { ReaderSettings } from '../readerSettingsSchema';
import { SETTINGS_INDEX } from './settingsIndex';

// Settings that are not in the index, each with the reason. Add a setting here only with a reason.
const UNINDEXED: Partial<Record<keyof ReaderSettings, string>> = {};

describe('SETTINGS_INDEX', () => {
  it('covers every default setting, or lists why it is left out', () => {
    const indexed = new Set(SETTINGS_INDEX.flatMap((entry) => entry.settingKeys));
    const missing = (Object.keys(defaultSettings) as (keyof ReaderSettings)[])
      .filter((key) => !indexed.has(key) && UNINDEXED[key] === undefined);
    expect(missing).toEqual([]);
  });

  it('has a unique id for every entry', () => {
    const ids = SETTINGS_INDEX.map((entry) => entry.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('gives every entry a keywords key named after its id', () => {
    SETTINGS_INDEX.forEach((entry) => {
      expect(entry.keywordsKey).toBe(`readerSettingsSearch.${entry.id}`);
    });
  });
});
