import { decomposeColor } from '@mui/material/styles';
import { availableLanguages } from '@utils/Misc';
import { TTS_NUMERIC_RANGES, TTS_ENUM_VALUES, TTS_RECORD_KEYS, isValidTtsPref, type TtsPrefs } from './tts/ttsTypes';
import { defaultSettings } from './readerDefaults';

export type EdgeTapBehavior = 'none' | 'scrollUp' | 'scrollDown' | 'chapter';
export type MarkReadBehavior = 'none' | 'button' | 'automatic' | 'buttonAutomatic';
export type SwipeGesture = 'none' | 'prevChapter' | 'nextChapter';
export type KeyAction = 'none' | 'scrollUp' | 'scrollDown' | 'prevChapter' | 'nextChapter' | 'toggleControls' | 'displaySheet' | 'fullscreen';
export type ControlsTrigger = 'singleTap' | 'doubleTap' | 'longPress' | 'off';
export type DimGestureSide = 'off' | 'left' | 'right';
export type ReaderHeaderBehavior = 'reappear' | 'pageTop';
export const DISPLAY_MODULES = ['size', 'line', 'para', 'margin', 'indent', 'align', 'theme', 'font', 'dim', 'warm'] as const;
export type DisplayModule = typeof DISPLAY_MODULES[number];

export interface ReaderSettings extends TtsPrefs {
  fontSize: number;
  fontFamily: string | null;
  textAlign: 'left' | 'center' | 'justify' | 'right';
  fontColor: string | null;
  backgroundColor: string | null;
  margin: number;
  lineSpacing: number;
  wordSpacing: number;
  letterSpacing: number;
  dimLevel: number;
  leftEdgeTapBehavior: EdgeTapBehavior;
  rightEdgeTapBehavior: EdgeTapBehavior;
  textSelectable: boolean;
  savePosition: boolean;
  markReadBehavior: MarkReadBehavior;
  keyboardNavigation: boolean;
  keyArrowLeft: KeyAction;
  keyArrowRight: KeyAction;
  keyArrowUp: KeyAction;
  keyArrowDown: KeyAction;
  keyPageUp: KeyAction;
  keyPageDown: KeyAction;
  keySpace: KeyAction;
  keyC: KeyAction;
  keyD: KeyAction;
  keyF: KeyAction;
  swipeLeftGesture: SwipeGesture;
  swipeRightGesture: SwipeGesture;
  hideScrollbar: boolean;
  paragraphIndent: boolean;
  paragraphSpacing: number;
  controlsTrigger: ControlsTrigger;
  dimGestureSide: DimGestureSide;
  dimGestureWidth: number;
  readerHeaderBehavior: ReaderHeaderBehavior;
  displaySheetModules: DisplayModule[];
  nightMode: boolean;
  nightModeStrength: number;
  nightModeScheduleEnabled: boolean;
  nightModeStartTime: string;
  nightModeEndTime: string;
}

const NUMERIC_RANGES: Partial<Record<keyof ReaderSettings, [number, number]>> = {
  ...(TTS_NUMERIC_RANGES as Partial<Record<keyof ReaderSettings, [number, number]>>),
  fontSize: [12, 32],
  margin: [-2, 22],
  lineSpacing: [1, 3],
  wordSpacing: [-2, 10],
  letterSpacing: [-1, 5],
  paragraphSpacing: [1, 3],
  dimLevel: [0, 90],
  dimGestureWidth: [5, 30],
  nightModeStrength: [10, 90],
};

const KEY_ACTIONS: readonly KeyAction[] = ['none', 'scrollUp', 'scrollDown', 'prevChapter', 'nextChapter', 'toggleControls', 'displaySheet', 'fullscreen'];

const ENUM_VALUES: Partial<Record<keyof ReaderSettings, readonly string[]>> = {
  ...(TTS_ENUM_VALUES as Partial<Record<keyof ReaderSettings, readonly string[]>>),
  textAlign: ['left', 'center', 'justify', 'right'],
  leftEdgeTapBehavior: ['none', 'scrollUp', 'scrollDown', 'chapter'],
  rightEdgeTapBehavior: ['none', 'scrollUp', 'scrollDown', 'chapter'],
  markReadBehavior: ['none', 'button', 'automatic', 'buttonAutomatic'],
  swipeLeftGesture: ['none', 'prevChapter', 'nextChapter'],
  swipeRightGesture: ['none', 'prevChapter', 'nextChapter'],
  keyArrowLeft: KEY_ACTIONS,
  keyArrowRight: KEY_ACTIONS,
  keyArrowUp: KEY_ACTIONS,
  keyArrowDown: KEY_ACTIONS,
  keyPageUp: KEY_ACTIONS,
  keyPageDown: KEY_ACTIONS,
  keySpace: KEY_ACTIONS,
  keyC: KEY_ACTIONS,
  keyD: KEY_ACTIONS,
  keyF: KEY_ACTIONS,
  controlsTrigger: ['singleTap', 'doubleTap', 'longPress', 'off'],
  dimGestureSide: ['off', 'left', 'right'],
  readerHeaderBehavior: ['reappear', 'pageTop'],
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

// Keeps two-letter language codes with a short voice name. Novels can be in languages outside the UI list.
const sanitizeVoiceMap = (value: unknown): Record<string, string> | undefined => {
  if (!isRecord(value)) return undefined;
  const cleaned: Record<string, string> = {};
  Object.entries(value).forEach(([lang, voice]) => {
    if (/^[a-z]{2}$/.test(lang) && typeof voice === 'string' && voice.length <= 300) {
      cleaned[lang] = voice;
    }
  });
  return cleaned;
};

// Known modules only, without repeats, order kept. An empty list drops the key so the default applies.
const sanitizeModules = (value: unknown): DisplayModule[] | undefined => {
  if (!Array.isArray(value)) return undefined;
  const modules = [...new Set(value)].filter((m): m is DisplayModule => DISPLAY_MODULES.includes(m));
  return modules.length > 0 ? modules : undefined;
};

// Blank strings must not become 0 through Number('')
const toNumber = (value: unknown): number => {
  if (typeof value === 'number') return value;
  return typeof value === 'string' && value.trim() !== '' ? Number(value) : NaN;
};

const sanitizeNumber = (key: keyof ReaderSettings, value: unknown): number | undefined => {
  const num = toNumber(value);
  const range = NUMERIC_RANGES[key];
  const inRange = !range || (num >= range[0] && num <= range[1]);
  return Number.isFinite(num) && inRange && isValidTtsPref(key, num) ? num : undefined;
};

const sanitizeString = (key: keyof ReaderSettings, value: string): string | undefined => {
  const allowed = ENUM_VALUES[key];
  if (allowed) return allowed.includes(value) ? value : undefined;
  if (key === 'nightModeStartTime' || key === 'nightModeEndTime') {
    return /^\d{2}:\d{2}$/.test(value) ? value : undefined;
  }
  if (key === 'ttsLanguage') return value === '' || availableLanguages.includes(value) ? value : undefined;
  return undefined;
};

// A colour the theme maths can read (hex, rgb, hsl). Anything else would throw in the contrast check.
const isValidColor = (value: string): boolean => {
  try {
    decomposeColor(value);
    return true;
  } catch {
    return false;
  }
};

const COLOR_KEYS: readonly string[] = ['fontColor', 'backgroundColor'];

// Returns the value to keep for `key`, or undefined when it is invalid
const sanitizeValue = (key: keyof ReaderSettings, value: unknown): unknown => {
  const def = defaultSettings[key];
  if ((TTS_RECORD_KEYS as readonly string[]).includes(key)) return sanitizeVoiceMap(value);
  if (key === 'displaySheetModules') return sanitizeModules(value);
  // Null defaults (fontFamily/fontColor/backgroundColor) accept null or a short string
  if (def === null) {
    if (COLOR_KEYS.includes(key)) {
      return value === null || (typeof value === 'string' && isValidColor(value)) ? value : undefined;
    }
    return value === null || (typeof value === 'string' && value.length <= 200) ? value : undefined;
  }
  if (typeof def === 'boolean') return typeof value === 'boolean' ? value : undefined;
  if (typeof def === 'number') return sanitizeNumber(key, value);
  if (typeof def === 'string' && typeof value === 'string') return sanitizeString(key, value);
  return undefined;
};

// Old cookies and v1.0 exports only know centerTapToOpenSettings. An explicit controlsTrigger wins.
const withLegacyControlsTrigger = (raw: Record<string, unknown>): Record<string, unknown> => {
  const legacy = raw.centerTapToOpenSettings;
  if (typeof legacy !== 'boolean' || sanitizeValue('controlsTrigger', raw.controlsTrigger) !== undefined) return raw;
  return { ...raw, controlsTrigger: legacy ? 'singleTap' : 'off' };
};

// 'narrated' used to be an engine. It is now the audiobook preference, and the engine goes back to its default.
const withLegacyNarrated = (raw: Record<string, unknown>): Record<string, unknown> => {
  if (raw.ttsEngine !== 'narrated') return raw;
  return { ...raw, ttsEngine: defaultSettings.ttsEngine, ttsPreferAudiobook: true };
};

// The one validator: stored values, cookie migration and file import all go through it.
export const sanitizeSettings = (raw: unknown): Partial<ReaderSettings> => {
  if (!isRecord(raw)) return {};
  const input = withLegacyNarrated(withLegacyControlsTrigger(raw));
  const result: Record<string, unknown> = {};
  (Object.keys(defaultSettings) as (keyof ReaderSettings)[]).forEach((key) => {
    if (!(key in input)) return;
    const value = sanitizeValue(key, input[key]);
    if (value !== undefined) result[key] = value;
  });
  return result as Partial<ReaderSettings>;
};
