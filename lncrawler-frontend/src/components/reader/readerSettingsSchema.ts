import { decomposeColor } from '@mui/material/styles';
import { availableLanguages } from '@utils/Misc';
import { TTS_NUMERIC_RANGES, TTS_ENUM_VALUES, TTS_RECORD_KEYS, isValidTtsPref, type TtsPrefs } from './tts/ttsTypes';
import { defaultSettings } from './readerDefaults';

export type EdgeTapBehavior = 'none' | 'scrollUp' | 'scrollDown' | 'chapter';
export type MarkReadBehavior = 'none' | 'button' | 'automatic' | 'buttonAutomatic';
export type SwipeGesture = 'none' | 'prevChapter' | 'nextChapter' | 'chapterList' | 'comments';
export type KeyAction = 'none' | 'scrollUp' | 'scrollDown' | 'prevChapter' | 'nextChapter' | 'toggleControls' | 'displaySheet' | 'fullscreen' | 'comments';
export type CenterAction = 'none' | 'controls' | 'fullscreen';
export type DimGestureSide = 'off' | 'left' | 'right';
export type ReaderHeaderBehavior = 'reappear' | 'pageTop';
export type ReadingMode = 'chapter' | 'infinite';
export const DISPLAY_MODULES = ['size', 'line', 'para', 'margin', 'indent', 'align', 'theme', 'font', 'dim', 'warm'] as const;
export type DisplayModule = typeof DISPLAY_MODULES[number];
export const OVERLAY_ITEMS = ['time12', 'time24', 'chapterPage', 'chapterSlider', 'chapterPercent', 'battery', 'bookPercent', 'bookChapter', 'dimness'] as const;
export type OverlayItem = typeof OVERLAY_ITEMS[number];
export type OverlayPosition = 'top' | 'bottom';
export type OverlaySize = 'full' | 'center' | 'left' | 'right';

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
  readingMode: ReadingMode;
  infiniteShowComments: boolean;
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
  keyM: KeyAction;
  swipeLeftGesture: SwipeGesture;
  swipeRightGesture: SwipeGesture;
  hideScrollbar: boolean;
  paragraphIndent: boolean;
  paragraphSpacing: number;
  centerSingleTap: CenterAction;
  centerDoubleTap: CenterAction;
  centerLongPress: CenterAction;
  dimGestureSide: DimGestureSide;
  dimGestureWidth: number;
  readerHeaderBehavior: ReaderHeaderBehavior;
  displaySheetModules: DisplayModule[];
  overlayEnabled: boolean;
  overlayPosition: OverlayPosition;
  overlaySize: OverlaySize;
  overlayEdgeOffset: number;
  overlayItems: OverlayItem[];
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
  overlayEdgeOffset: [0, 80],
  nightModeStrength: [10, 90],
};

const KEY_ACTIONS: readonly KeyAction[] = ['none', 'scrollUp', 'scrollDown', 'prevChapter', 'nextChapter', 'toggleControls', 'displaySheet', 'fullscreen', 'comments'];

const ENUM_VALUES: Partial<Record<keyof ReaderSettings, readonly string[]>> = {
  ...(TTS_ENUM_VALUES as Partial<Record<keyof ReaderSettings, readonly string[]>>),
  textAlign: ['left', 'center', 'justify', 'right'],
  leftEdgeTapBehavior: ['none', 'scrollUp', 'scrollDown', 'chapter'],
  rightEdgeTapBehavior: ['none', 'scrollUp', 'scrollDown', 'chapter'],
  markReadBehavior: ['none', 'button', 'automatic', 'buttonAutomatic'],
  readingMode: ['chapter', 'infinite'],
  swipeLeftGesture: ['none', 'prevChapter', 'nextChapter', 'chapterList', 'comments'],
  swipeRightGesture: ['none', 'prevChapter', 'nextChapter', 'chapterList', 'comments'],
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
  keyM: KEY_ACTIONS,
  centerSingleTap: ['none', 'controls', 'fullscreen'],
  centerDoubleTap: ['none', 'controls', 'fullscreen'],
  centerLongPress: ['none', 'controls', 'fullscreen'],
  dimGestureSide: ['off', 'left', 'right'],
  readerHeaderBehavior: ['reappear', 'pageTop'],
  overlayPosition: ['top', 'bottom'],
  overlaySize: ['full', 'center', 'left', 'right'],
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

// Known overlay items only, without repeats, order kept. An empty list is valid: the overlay then shows nothing.
const sanitizeOverlayItems = (value: unknown): OverlayItem[] | undefined => {
  if (!Array.isArray(value)) return undefined;
  return [...new Set(value)].filter((item): item is OverlayItem => OVERLAY_ITEMS.includes(item));
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
  if (key === 'overlayItems') return sanitizeOverlayItems(value);
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

const CENTER_KEYS = ['centerSingleTap', 'centerDoubleTap', 'centerLongPress'] as const;
const LEGACY_TRIGGER_KEY: Record<string, (typeof CENTER_KEYS)[number]> = {
  singleTap: 'centerSingleTap',
  doubleTap: 'centerDoubleTap',
  longPress: 'centerLongPress',
};

// Old cookies and exports held one controls trigger (or, before it, centerTapToOpenSettings).
// It becomes the slot that shows the controls; the other slots take their defaults, never 'controls'.
// Explicit centre settings win.
const withLegacyControlsTrigger = (raw: Record<string, unknown>): Record<string, unknown> => {
  if (CENTER_KEYS.some((key) => key in raw)) return raw;
  let trigger = raw.controlsTrigger;
  if (typeof trigger !== 'string' || !(trigger === 'off' || trigger in LEGACY_TRIGGER_KEY)) {
    const legacy = raw.centerTapToOpenSettings;
    if (typeof legacy !== 'boolean') return raw;
    trigger = legacy ? 'singleTap' : 'off';
  }
  const migrated: Record<string, unknown> = { ...raw };
  CENTER_KEYS.forEach((key) => {
    migrated[key] = LEGACY_TRIGGER_KEY[trigger as string] === key
      ? 'controls'
      : defaultSettings[key] === 'controls' ? 'none' : defaultSettings[key];
  });
  return migrated;
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
