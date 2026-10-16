import type { KokoroDevice, NeuralOptions, SupertonicDevice } from './voiceCatalog';
import type { HighlightMode } from './textSegments';

export type TtsEngineChoice = 'browser' | 'neural';
export type { HighlightMode as TtsHighlightMode, KokoroDevice as TtsKokoroDevice };

/** Text-to-speech preferences, persisted with the other reader settings. */
export interface TtsPrefs {
  /** Device voices (Web Speech) or downloadable HD voices. */
  ttsEngine: TtsEngineChoice;
  /** Chosen device voice per language: { lang: voiceURI }. */
  ttsBrowserVoices: Record<string, string>;
  /** Chosen HD voice per language: { lang: 'piper:…' | 'kokoro:…' }. */
  ttsNeuralVoices: Record<string, string>;
  /** Language used to read; '' follows the novel's language. */
  ttsLanguage: string;
  ttsRate: number;
  /** Device voices only. */
  ttsPitch: number;
  ttsVolume: number;
  ttsHighlight: HighlightMode;
  ttsAutoScroll: boolean;
  ttsAutoNextChapter: boolean;
  ttsReadTitle: boolean;
  ttsSkipNotes: boolean;
  /** Extra silence between paragraphs, in ms (scaled by the speed). */
  ttsParagraphPause: number;
  /** While the player is open, tapping a paragraph reads from there. */
  ttsTapToSeek: boolean;
  /** Keep the screen awake while reading aloud. */
  ttsKeepScreenOn: boolean;
  ttsKokoroDevice: KokoroDevice;
  ttsSupertonicDevice: SupertonicDevice;
  /** Supertonic denoising steps (4 fast, 6 balanced, 8 best). */
  ttsSupertonicSteps: number;
}

export const defaultTtsPrefs: TtsPrefs = {
  ttsEngine: 'browser',
  ttsBrowserVoices: {},
  ttsNeuralVoices: {},
  ttsLanguage: '',
  ttsRate: 1,
  ttsPitch: 1,
  ttsVolume: 1,
  ttsHighlight: 'sentence',
  ttsAutoScroll: true,
  ttsAutoNextChapter: true,
  ttsReadTitle: true,
  ttsSkipNotes: true,
  ttsParagraphPause: 250,
  ttsTapToSeek: true,
  ttsKeepScreenOn: true,
  ttsKokoroDevice: 'wasm',
  ttsSupertonicDevice: 'auto',
  ttsSupertonicSteps: 6,
};

export const TTS_NUMERIC_RANGES = {
  ttsRate: [0.5, 3],
  ttsPitch: [0.5, 2],
  ttsVolume: [0, 1],
  ttsParagraphPause: [0, 2000],
  ttsSupertonicSteps: [2, 12],
} as const;

export const TTS_ENUM_VALUES = {
  ttsEngine: ['browser', 'neural'],
  ttsHighlight: ['none', 'paragraph', 'sentence'],
  ttsKokoroDevice: ['wasm', 'webgpu'],
  ttsSupertonicDevice: ['auto', 'wasm', 'webgpu'],
} as const;

/** Keys whose value is a { lang: string } map. */
export const TTS_RECORD_KEYS = ['ttsBrowserVoices', 'ttsNeuralVoices'] as const;

export const TTS_RATE_STEPS = [0.5, 0.75, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3];

/** Approximate height of the player bar, reserved under the content. */
export const TTS_BAR_HEIGHT = { mobile: 132, desktop: 120 };

/**
 * Range/enum check for a stored TTS value (cookies can be edited by hand).
 * Returns true for keys that aren't TTS preferences.
 */
export function isValidTtsPref(key: string, value: unknown): boolean {
  if (key in TTS_NUMERIC_RANGES) {
    const [min, max] = TTS_NUMERIC_RANGES[key as keyof typeof TTS_NUMERIC_RANGES];
    if (key === 'ttsSupertonicSteps' && !Number.isInteger(value)) return false;
    return typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max;
  }
  if (key in TTS_ENUM_VALUES) {
    return (TTS_ENUM_VALUES[key as keyof typeof TTS_ENUM_VALUES] as readonly unknown[]).includes(value);
  }
  if ((TTS_RECORD_KEYS as readonly string[]).includes(key)) {
    return value !== null && typeof value === 'object' && !Array.isArray(value)
      && Object.values(value).every(v => typeof v === 'string');
  }
  if (key === 'ttsLanguage') return typeof value === 'string' && /^([a-z]{2})?$/.test(value);
  return true;
}

/** The engine options the TTS worker needs from the preferences. */
export const neuralOptions = (p: TtsPrefs): NeuralOptions => ({
  kokoroDevice: p.ttsKokoroDevice,
  supertonicDevice: p.ttsSupertonicDevice,
  supertonicSteps: p.ttsSupertonicSteps,
});

/** Stable key of the options, to know when generated audio is stale. */
export const neuralOptionsKey = (o: NeuralOptions): string =>
  `${o.kokoroDevice}|${o.supertonicDevice}|${o.supertonicSteps}`;
