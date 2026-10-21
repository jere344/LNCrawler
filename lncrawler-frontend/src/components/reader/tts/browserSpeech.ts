/**
 * Thin promise wrapper around the Web Speech API (the device's own voices).
 */

export const isBrowserSpeechSupported = (): boolean =>
  typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;

let voicesPromise: Promise<SpeechSynthesisVoice[]> | null = null;

// Anti-fingerprinting user scripts wrap getVoices() and can throw or return
// holes; a throw here would escape the effect and crash the reader.
function readVoices(): SpeechSynthesisVoice[] {
  try {
    return (speechSynthesis.getVoices() ?? []).filter(Boolean);
  } catch {
    return [];
  }
}

/** Voices load asynchronously in Chrome; wait for them (up to 3s). */
export function getBrowserVoices(): Promise<SpeechSynthesisVoice[]> {
  if (!isBrowserSpeechSupported()) return Promise.resolve([]);
  const now = readVoices();
  if (now.length) return Promise.resolve(now);
  voicesPromise ??= new Promise(resolve => {
    const done = () => {
      speechSynthesis.removeEventListener('voiceschanged', done);
      resolve(readVoices());
    };
    speechSynthesis.addEventListener('voiceschanged', done);
    setTimeout(done, 3000);
  });
  return voicesPromise.then(voices => {
    if (!voices.length) voicesPromise = null;
    return voices;
  });
}

const normalizeLang = (lang: string) => lang.toLowerCase().replace('_', '-');

// Names that usually indicate a natural sounding (neural / premium) voice.
const QUALITY_HINTS = /natural|neural|online|premium|enhanced|google|siri/i;

/** Voices for a two-letter language, best sounding first. */
export function voicesForLang(voices: SpeechSynthesisVoice[], lang: string): SpeechSynthesisVoice[] {
  const code = lang.toLowerCase();
  // Chinese voices may be tagged "cmn"/"yue" on some platforms.
  const aliases = code === 'zh' ? ['zh', 'cmn', 'yue'] : [code];
  return voices
    .filter(v => aliases.some(a => normalizeLang(v.lang) === a || normalizeLang(v.lang).startsWith(`${a}-`)))
    .sort((a, b) => {
      const qa = QUALITY_HINTS.test(a.name) ? 0 : 1;
      const qb = QUALITY_HINTS.test(b.name) ? 0 : 1;
      if (qa !== qb) return qa - qb;
      if (a.default !== b.default) return a.default ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
}

export function pickBrowserVoice(
  voices: SpeechSynthesisVoice[],
  lang: string,
  preferredUri: string | undefined,
): SpeechSynthesisVoice | undefined {
  const forLang = voicesForLang(voices, lang);
  return forLang.find(v => v.voiceURI === preferredUri) ?? forLang[0];
}

export interface SpeakOptions {
  voice?: SpeechSynthesisVoice;
  lang: string;
  rate: number;
  pitch: number;
  volume: number;
}

// Chrome drops `onend` when the utterance object is garbage collected, so the
// current one is kept referenced here.
let current: SpeechSynthesisUtterance | null = null;

/**
 * Speak `text`. Resolves `true` when it finished, `false` when it was
 * cancelled. Rejects on a real synthesis error.
 */
export function speak(text: string, opts: SpeakOptions): Promise<boolean> {
  return new Promise((resolve, reject) => {
    const u = new SpeechSynthesisUtterance(text);
    if (opts.voice) u.voice = opts.voice;
    u.lang = opts.voice?.lang ?? opts.lang;
    // Web Speech accepts 0.1–10 but most voices distort above 2.
    u.rate = Math.min(opts.rate, 4);
    u.pitch = opts.pitch;
    u.volume = opts.volume;

    let settled = false;
    // Some engines never fire onend (e.g. after the tab was backgrounded on
    // Android); don't hang forever.
    const watchdog = window.setTimeout(
      () => finish(true),
      Math.max(8000, (text.length / 8) * 1000 / Math.max(opts.rate, 0.25) * 3),
    );
    const finish = (ok: boolean, err?: Error) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(watchdog);
      if (current === u) current = null;
      if (err) reject(err);
      else resolve(ok);
    };
    u.onend = () => finish(true);
    u.onerror = e => {
      if (e.error === 'interrupted' || e.error === 'canceled') finish(false);
      else finish(false, new Error(e.error || 'speech error'));
    };

    current = u;
    speechSynthesis.speak(u);
    // Chrome sometimes starts in a paused state after a previous cancel().
    if (speechSynthesis.paused) speechSynthesis.resume();
  });
}

export function cancelSpeech(): void {
  if (isBrowserSpeechSupported()) speechSynthesis.cancel();
}
