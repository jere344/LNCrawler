import { describe, it, expect } from 'vitest';
import { sanitizeSettings } from './readerSettingsSchema';
import { defaultSettings } from './readerDefaults';

describe('sanitizeSettings', () => {
  it('keeps the defaults unchanged', () => {
    expect(sanitizeSettings(defaultSettings)).toEqual(defaultSettings);
  });

  it('rejects out-of-range numbers', () => {
    expect(sanitizeSettings({ fontSize: 99 })).toEqual({});
    expect(sanitizeSettings({ dimGestureWidth: 4 })).toEqual({});
    expect(sanitizeSettings({ dimGestureWidth: 30 })).toEqual({ dimGestureWidth: 30 });
  });

  it('accepts numeric strings but not blank ones', () => {
    expect(sanitizeSettings({ fontSize: '20' })).toEqual({ fontSize: 20 });
    expect(sanitizeSettings({ fontSize: '  ' })).toEqual({});
    expect(sanitizeSettings({ fontSize: 'big' })).toEqual({});
  });

  it('rejects bad enum values', () => {
    expect(sanitizeSettings({ controlsTrigger: 'tripleTap' })).toEqual({});
    expect(sanitizeSettings({ dimGestureSide: 'top' })).toEqual({});
    expect(sanitizeSettings({ keyC: 'bogus' })).toEqual({});
    expect(sanitizeSettings({ keyC: 'displaySheet' })).toEqual({ keyC: 'displaySheet' });
  });

  it('handles null colours', () => {
    expect(sanitizeSettings({ fontColor: null })).toEqual({ fontColor: null });
    expect(sanitizeSettings({ fontColor: '#fff' })).toEqual({ fontColor: '#fff' });
    expect(sanitizeSettings({ fontColor: 'x'.repeat(201) })).toEqual({});
    expect(sanitizeSettings({ backgroundColor: 12 })).toEqual({});
  });

  it('drops colours the theme cannot parse', () => {
    expect(sanitizeSettings({ fontColor: 'not a colour' })).toEqual({});
    expect(sanitizeSettings({ backgroundColor: 'bogus(1, 2, 3)' })).toEqual({});
    expect(sanitizeSettings({ backgroundColor: 'rgb(10, 20, 30)' })).toEqual({ backgroundColor: 'rgb(10, 20, 30)' });
  });

  it('cleans voice records', () => {
    expect(sanitizeSettings({ ttsBrowserVoices: { en: 'Alex', XYZ: 'Unknown', fr: 3 } }))
      .toEqual({ ttsBrowserVoices: { en: 'Alex' } });
    expect(sanitizeSettings({ ttsNeuralVoices: { en: 'v'.repeat(301) } })).toEqual({ ttsNeuralVoices: {} });
    expect(sanitizeSettings({ ttsBrowserVoices: ['en'] })).toEqual({});
  });

  it('keeps two-letter language codes outside the UI list', () => {
    expect(sanitizeSettings({ ttsBrowserVoices: { cs: 'Zuzana' } })).toEqual({ ttsBrowserVoices: { cs: 'Zuzana' } });
    expect(sanitizeSettings({ ttsNeuralVoices: { cs: 'v', CS: 'x', czech: 'y' } })).toEqual({ ttsNeuralVoices: { cs: 'v' } });
  });

  it('keeps known display modules once, in order', () => {
    expect(sanitizeSettings({ displaySheetModules: ['dim', 'size', 'dim', 'nope'] }))
      .toEqual({ displaySheetModules: ['dim', 'size'] });
  });

  it('drops display modules when none is valid', () => {
    expect(sanitizeSettings({ displaySheetModules: ['nope'] })).toEqual({});
    expect(sanitizeSettings({ displaySheetModules: [] })).toEqual({});
    expect(sanitizeSettings({ displaySheetModules: 'size' })).toEqual({});
  });

  it('maps centerTapToOpenSettings to controlsTrigger', () => {
    expect(sanitizeSettings({ centerTapToOpenSettings: true })).toEqual({ controlsTrigger: 'singleTap' });
    expect(sanitizeSettings({ centerTapToOpenSettings: false })).toEqual({ controlsTrigger: 'off' });
  });

  it('lets an explicit controlsTrigger win over the legacy key', () => {
    expect(sanitizeSettings({ centerTapToOpenSettings: false, controlsTrigger: 'doubleTap' }))
      .toEqual({ controlsTrigger: 'doubleTap' });
  });

  it('returns an empty object for non-object input', () => {
    for (const raw of [null, undefined, 5, 'settings', [1, 2]]) {
      expect(sanitizeSettings(raw)).toEqual({});
    }
  });

  it('ignores unknown keys', () => {
    expect(sanitizeSettings({ exportDate: '2026-01-01', version: '1.0', fontSize: 20 })).toEqual({ fontSize: 20 });
  });

  it('keeps the audiobook preference as a boolean', () => {
    expect(sanitizeSettings({ ttsPreferAudiobook: true })).toEqual({ ttsPreferAudiobook: true });
    expect(sanitizeSettings({ ttsPreferAudiobook: 'yes' })).toEqual({});
  });

  it('turns the old narrated engine into the audiobook preference', () => {
    expect(sanitizeSettings({ ttsEngine: 'narrated' })).toEqual({
      ttsEngine: defaultSettings.ttsEngine,
      ttsPreferAudiobook: true,
    });
  });

  it('keeps the browser and HD engines', () => {
    expect(sanitizeSettings({ ttsEngine: 'neural' })).toEqual({ ttsEngine: 'neural' });
    expect(sanitizeSettings({ ttsEngine: 'browser' })).toEqual({ ttsEngine: 'browser' });
    expect(sanitizeSettings({ ttsEngine: 'other' })).toEqual({});
  });
});
