import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { neuralOptions, neuralOptionsKey, type TtsPrefs } from './ttsTypes';
import { useWakeLock } from './useWakeLock';
import {
  buildDocument,
  clearHighlight,
  ensureHighlightStyle,
  firstVisibleBlock,
  getBlocks,
  getContentRoot,
  highlightChunk,
  blockIndexOf,
  type TtsDocument,
} from './textSegments';
import {
  cancelSpeech,
  getBrowserVoices,
  isBrowserSpeechSupported,
  pickBrowserVoice,
  speak,
} from './browserSpeech';
import {
  cancelJobs,
  isNeuralSupported,
  isVoiceDownloaded,
  prepareVoice,
  synthesize,
  wavToUrl,
  type SynthJob,
} from './neuralClient';
import { hasNeuralVoices, resolveNeuralVoice, type NeuralVoice } from './voiceCatalog';
import { nextBlockChunk, previousBlockChunk } from './ttsChunks';

export type TtsStatus =
  | 'idle'          // bar open, nothing playing yet / finished
  | 'preparing'     // loading a voice model or the next chapter
  | 'playing'
  | 'paused'
  | 'needsDownload' // HD voice selected but not on this device yet
  | 'error';

export type TtsErrorKind = 'unsupported' | 'noVoice' | 'neuralFailed' | 'noContent';

export type SleepTimer =
  | { mode: 'off' }
  | { mode: 'chapter' }
  | { mode: 'time'; endsAt: number };

export interface UseTtsPlayerArgs {
  prefs: TtsPrefs;
  /** Two-letter language the text is read in. */
  lang: string;
  /** Changes for every chapter; null while a chapter is loading. */
  chapterKey: string | null;
  chapterTitle: string;
  novelTitle: string;
  artwork?: string | null;
  hasNextChapter: boolean;
  onNextChapter: () => void;
  /** Persist one TTS preference (used by the "switch engine" shortcuts). */
  onPrefChange: <K extends keyof TtsPrefs>(key: K, value: TtsPrefs[K]) => void;
  highlightColors: { block: string; sentence: string };
  /** Height of sticky UI at the top of the viewport (toolbar). */
  topOffset: number;
  /** Height of the player bar, so auto-scroll keeps text above it. */
  bottomOffset: number;
}

const AUTOSCROLL_IDLE_MS = 4000;
const PREFETCH_AHEAD = 2;

/** 10 s of silence: keeps the media session (lock screen controls) alive
 *  while device voices speak, since speechSynthesis has none of its own. */
function makeSilenceUrl(): string {
  const rate = 8000;
  const samples = rate * 10;
  const buffer = new ArrayBuffer(44 + samples * 2);
  const v = new DataView(buffer);
  const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, 'RIFF'); v.setUint32(4, 36 + samples * 2, true); w(8, 'WAVE'); w(12, 'fmt ');
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true);
  v.setUint16(34, 16, true); w(36, 'data'); v.setUint32(40, samples * 2, true);
  return URL.createObjectURL(new Blob([buffer], { type: 'audio/wav' }));
}

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

export function useTtsPlayer(args: UseTtsPlayerArgs) {
  const {
    prefs, lang, chapterKey, chapterTitle, novelTitle, artwork, highlightColors,
  } = args;

  const [open, setOpen] = useState(false);
  const [status, setStatusState] = useState<TtsStatus>('idle');
  const [errorKind, setErrorKind] = useState<TtsErrorKind | null>(null);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const [chunkIndex, setChunkIndex] = useState(-1);
  const [blockIndex, setBlockIndex] = useState(-1);
  const [blockCount, setBlockCount] = useState(0);
  const [download, setDownload] = useState<{ loaded: number; total: number } | null>(null);
  const [sleepTimer, setSleepTimer] = useState<SleepTimer>({ mode: 'off' });
  // HD voice failed this session: read with device voices instead.
  const [neuralFallback, setNeuralFallback] = useState(false);

  // Latest values for the async loop, which outlives renders.
  const argsRef = useRef(args);
  argsRef.current = args;
  const statusRef = useRef<TtsStatus>('idle');
  const sleepRef = useRef(sleepTimer);
  sleepRef.current = sleepTimer;

  const docRef = useRef<TtsDocument | null>(null);
  const indexRef = useRef(-1);
  const runRef = useRef(0);
  const pausedRef = useRef(false);
  const autoplayPendingRef = useRef(false);
  const userScrollAtRef = useRef(0);
  const confirmedDownloadsRef = useRef(new Set<string>());

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const keepAliveRef = useRef<HTMLAudioElement | null>(null);
  const endAudioRef = useRef<((finished: boolean) => void) | null>(null);
  const prefetchRef = useRef(new Map<number, SynthJob>());
  const audioUrlRef = useRef<string | null>(null);
  const bakedVolumeRef = useRef(1);
  const prefetchKeyRef = useRef('');
  // Screen wake lock, held while playing (keep screen on setting)
  const { acquireWakeLock, releaseWakeLock } = useWakeLock(argsRef);

  const setStatus = useCallback((s: TtsStatus) => {
    statusRef.current = s;
    setStatusState(s);
  }, []);

  // ------------------------------------------------------------------------
  // Engine selection
  // ------------------------------------------------------------------------

  const neuralVoice: NeuralVoice | undefined = useMemo(() => {
    if (prefs.ttsEngine !== 'neural' || neuralFallback || !isNeuralSupported()) return undefined;
    return resolveNeuralVoice(lang, prefs.ttsNeuralVoices);
  }, [prefs.ttsEngine, prefs.ttsNeuralVoices, lang, neuralFallback]);

  /** 'neural' only when an HD voice exists for this language. */
  const engine: 'browser' | 'neural' = neuralVoice ? 'neural' : 'browser';
  const engineRef = useRef(engine);
  engineRef.current = engine;
  const neuralVoiceRef = useRef(neuralVoice);
  neuralVoiceRef.current = neuralVoice;

  // ------------------------------------------------------------------------
  // Output primitives
  // ------------------------------------------------------------------------

  const getAudio = () => {
    if (!audioRef.current) {
      const audio = new Audio();
      audio.preload = 'auto';
      (audio as HTMLAudioElement & { preservesPitch?: boolean }).preservesPitch = true;
      audioRef.current = audio;
    }
    return audioRef.current;
  };

  const startKeepAlive = () => {
    if (engineRef.current !== 'browser') return;
    if (!keepAliveRef.current) {
      const a = new Audio(makeSilenceUrl());
      a.loop = true;
      keepAliveRef.current = a;
    }
    keepAliveRef.current.play().catch(() => undefined);
  };
  const stopKeepAlive = () => keepAliveRef.current?.pause();


  const clearPrefetch = () => {
    const jobs = prefetchRef.current;
    cancelJobs([...jobs.values()].map(j => j.id));
    jobs.clear();
  };

  /** Stop whatever is being spoken right now and invalidate the running loop. */
  const haltOutput = () => {
    runRef.current++;
    cancelSpeech();
    endAudioRef.current?.(false);
    endAudioRef.current = null;
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
    }
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
  };

  // ------------------------------------------------------------------------
  // Document
  // ------------------------------------------------------------------------

  const ensureDocument = (): TtsDocument | null => {
    if (docRef.current) return docRef.current;
    const root = getContentRoot();
    if (!root) return null;
    const { prefs: p, chapterTitle: title } = argsRef.current;
    const doc = buildDocument(root, { lang: argsRef.current.lang, skipNotes: p.ttsSkipNotes, title: p.ttsReadTitle ? title : undefined });
    docRef.current = doc;
    setBlockCount(doc.blockCount);
    clearPrefetch();
    return doc;
  };

  const invalidateDocument = () => {
    docRef.current = null;
    clearPrefetch();
  };

  /** Chunk index to start from when nothing is in progress: the first block
   *  on screen, or the title when the chapter is scrolled to the top. */
  const startingChunk = (doc: TtsDocument): number => {
    const root = getContentRoot();
    if (!root) return 0;
    const block = firstVisibleBlock(root, argsRef.current.topOffset);
    if (block === 0 && window.scrollY < 50) return 0;
    for (let b = block; b < doc.blockFirstChunk.length; b++) {
      if (doc.blockFirstChunk[b] !== -1) return doc.blockFirstChunk[b];
    }
    return 0;
  };

  const showChunk = (i: number) => {
    const doc = docRef.current;
    const root = getContentRoot();
    if (!doc || !root) return;
    const chunk = doc.chunks[i];
    if (!chunk) return;
    setBlockIndex(chunk.block);
    const { prefs: p, topOffset, bottomOffset } = argsRef.current;
    const target = highlightChunk(root, chunk, p.ttsHighlight);
    if (!target || !p.ttsAutoScroll) return;
    if (Date.now() - userScrollAtRef.current < AUTOSCROLL_IDLE_MS) return;
    const rangeRect = target.range?.getBoundingClientRect();
    const rect = rangeRect && rangeRect.height > 0 ? rangeRect : target.el.getBoundingClientRect();
    const top = topOffset + 16;
    const bottom = window.innerHeight - bottomOffset - 16;
    if (rect.top < top || rect.bottom > bottom) {
      window.scrollBy({ top: rect.top - top - (bottom - top) * 0.25, behavior: 'smooth' });
    }
  };

  // ------------------------------------------------------------------------
  // Speaking one chunk
  // ------------------------------------------------------------------------

  const jobFor = (i: number): SynthJob | null => {
    const doc = docRef.current;
    const voice = neuralVoiceRef.current;
    if (!doc || !voice || i >= doc.chunks.length) return null;
    const options = neuralOptions(argsRef.current.prefs);
    const key = `${voice.id}|${neuralOptionsKey(options)}`;
    if (prefetchKeyRef.current !== key) {
      clearPrefetch();
      prefetchKeyRef.current = key;
    }
    let job = prefetchRef.current.get(i);
    if (!job) {
      job = synthesize(voice.id, options, doc.chunks[i].text);
      // Avoid unhandled rejections for jobs that end up cancelled.
      job.promise.catch(() => undefined);
      prefetchRef.current.set(i, job);
    }
    return job;
  };

  const dropJob = (i: number) => {
    const job = prefetchRef.current.get(i);
    if (!job) return;
    prefetchRef.current.delete(i);
  };

  const speakNeural = async (i: number, alive: () => boolean): Promise<boolean> => {
    const job = jobFor(i);
    if (!job) return false;
    // Drop stale jobs far behind, queue the next ones.
    prefetchRef.current.forEach((_, k) => { if (k < i) dropJob(k); });
    for (let k = 1; k <= PREFETCH_AHEAD; k++) jobFor(i + k);

    const { wav } = await job.promise;
    if (!alive()) return false;
    const audio = getAudio();
    const volume = argsRef.current.prefs.ttsVolume;
    const url = wavToUrl(wav, volume);
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    audioUrlRef.current = url;
    bakedVolumeRef.current = volume;
    audio.src = url;
    audio.playbackRate = argsRef.current.prefs.ttsRate;
    audio.volume = 1;
    const finished = await new Promise<boolean>((resolve, reject) => {
      endAudioRef.current = resolve;
      audio.onended = () => resolve(true);
      audio.onerror = () => reject(new Error('Audio playback failed'));
      if (!pausedRef.current) {
        audio.play().catch(err => {
          // Autoplay was blocked (e.g. iOS after a background chapter change).
          if ((err as DOMException).name === 'NotAllowedError') {
            pausedRef.current = true;
            setStatus('paused');
          } else if ((err as DOMException).name !== 'AbortError') {
            reject(err);
          }
        });
      }
    });
    endAudioRef.current = null;
    dropJob(i);
    return finished;
  };

  const speakBrowser = async (i: number): Promise<boolean> => {
    const doc = docRef.current;
    if (!doc) return false;
    const { prefs: p, lang: l } = argsRef.current;
    const voices = await getBrowserVoices();
    return speak(doc.chunks[i].text, {
      voice: pickBrowserVoice(voices, l, p.ttsBrowserVoices[l]),
      lang: l,
      rate: p.ttsRate,
      pitch: p.ttsPitch,
      volume: p.ttsVolume,
    });
  };

  // ------------------------------------------------------------------------
  // Main loop
  // ------------------------------------------------------------------------

  const fail = (kind: TtsErrorKind, detail?: string) => {
    haltOutput();
    stopKeepAlive();
    releaseWakeLock();
    setErrorKind(kind);
    setErrorDetail(detail ?? null);
    setStatus('error');
  };

  const runFrom = async (start: number) => {
    const run = ++runRef.current;
    const alive = () => run === runRef.current;
    const doc = docRef.current;
    if (!doc) return;
    pausedRef.current = false;
    setErrorKind(null);
    setStatus('playing');
    startKeepAlive();
    acquireWakeLock();

    for (let i = start; i < doc.chunks.length; i++) {
      if (!alive()) return;
      indexRef.current = i;
      setChunkIndex(i);
      showChunk(i);
      let finished: boolean;
      try {
        finished = engineRef.current === 'neural' ? await speakNeural(i, alive) : await speakBrowser(i);
      } catch (err) {
        if (!alive()) return;
        console.error('TTS error:', err);
        fail(engineRef.current === 'neural' ? 'neuralFailed' : 'noVoice', err instanceof Error ? err.message : undefined);
        return;
      }
      if (!alive() || !finished) return;

      const next = doc.chunks[i + 1];
      const pause = argsRef.current.prefs.ttsParagraphPause;
      if (next && next.block !== doc.chunks[i].block && pause > 0) {
        await sleep(pause / argsRef.current.prefs.ttsRate);
      }
    }
    if (!alive()) return;

    // End of chapter.
    clearHighlight();
    indexRef.current = -1;
    setChunkIndex(-1);
    if (sleepRef.current.mode === 'chapter') {
      setSleepTimer({ mode: 'off' });
      stopKeepAlive();
      releaseWakeLock();
      setStatus('idle');
      return;
    }
    if (argsRef.current.prefs.ttsAutoNextChapter && argsRef.current.hasNextChapter) {
      autoplayPendingRef.current = true;
      setStatus('preparing');
      argsRef.current.onNextChapter();
      return;
    }
    stopKeepAlive();
    releaseWakeLock();
    setStatus('idle');
  };

  /** Make sure the selected voice can be used, then play from `from`. */
  const begin = async (from?: number) => {
    // Stop any sentence still loaded (e.g. paused HD audio) and the loop
    // waiting on it, so it can't be replayed or run alongside the new one.
    haltOutput();
    setOpen(true);
    setErrorKind(null);
    const doc = ensureDocument();
    if (!doc || !doc.chunks.length) {
      fail('noContent');
      return;
    }
    const start = from ?? (indexRef.current >= 0 ? indexRef.current : startingChunk(doc));
    indexRef.current = start;
    setChunkIndex(start);

    if (engineRef.current === 'browser') {
      if (!isBrowserSpeechSupported()) {
        fail(hasNeuralVoices(argsRef.current.lang) && isNeuralSupported() ? 'noVoice' : 'unsupported');
        return;
      }
      runFrom(start);
      return;
    }

    const voice = neuralVoiceRef.current!;
    const options = neuralOptions(argsRef.current.prefs);
    if (!confirmedDownloadsRef.current.has(voice.id) && !(await isVoiceDownloaded(voice.id, options))) {
      showChunk(start);
      setStatus('needsDownload');
      return;
    }
    confirmedDownloadsRef.current.add(voice.id);
    const run = ++runRef.current;
    setStatus('preparing');
    // Touch the audio element inside the user gesture so iOS lets it play
    // later, once the voice has loaded.
    getAudio().play().catch(() => undefined);
    try {
      await prepareVoice(voice.id, options, (loaded, total) => {
        if (run === runRef.current) setDownload({ loaded, total });
      });
    } catch (err) {
      if (run !== runRef.current) return;
      setDownload(null);
      fail('neuralFailed', err instanceof Error ? err.message : undefined);
      return;
    }
    setDownload(null);
    if (run !== runRef.current) return;
    runFrom(indexRef.current);
  };

  // ------------------------------------------------------------------------
  // Public controls
  // ------------------------------------------------------------------------

  const play = useCallback(() => {
    const s = statusRef.current;
    if (s === 'playing' || s === 'preparing') return;
    // Only one audio source plays at a time: the global audiobook player pauses on this event.
    window.dispatchEvent(new Event('lncrawler:tts-play'));
    if (s === 'paused' && engineRef.current === 'neural' && endAudioRef.current && audioRef.current?.src) {
      // Resume mid-sentence.
      pausedRef.current = false;
      setStatus('playing');
      acquireWakeLock();
      audioRef.current.play().catch(() => undefined);
      return;
    }
    begin();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- uses refs only
  }, []);

  const pause = useCallback(() => {
    const s = statusRef.current;
    if (s !== 'playing' && s !== 'preparing') return;
    pausedRef.current = true;
    if (engineRef.current === 'neural' && s === 'playing') {
      audioRef.current?.pause();
    } else {
      // Device voices can't reliably pause mid-sentence (Android cancels):
      // restart the current sentence on resume instead.
      haltOutput();
    }
    autoplayPendingRef.current = false;
    stopKeepAlive();
    releaseWakeLock();
    setStatus('paused');
    // eslint-disable-next-line react-hooks/exhaustive-deps -- uses refs only
  }, []);

  const toggle = useCallback(() => {
    if (statusRef.current === 'playing' || statusRef.current === 'preparing') pause();
    else play();
  }, [play, pause]);

  /** Jump to chunk `i`, keeping the current play/pause state. */
  const seekToChunk = useCallback((i: number) => {
    const doc = docRef.current ?? ensureDocument();
    if (!doc) return;
    const target = Math.max(0, Math.min(i, doc.chunks.length - 1));
    const wasPlaying = statusRef.current === 'playing';
    haltOutput();
    indexRef.current = target;
    setChunkIndex(target);
    if (wasPlaying) {
      runFrom(target);
    } else {
      showChunk(target);
      if (statusRef.current !== 'needsDownload') setStatus(statusRef.current === 'idle' ? 'idle' : 'paused');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- uses refs only
  }, []);

  const skipBlock = useCallback((delta: 1 | -1) => {
    const doc = docRef.current ?? ensureDocument();
    if (!doc) return;
    const current = Math.max(0, indexRef.current);
    if (delta > 0) {
      const next = nextBlockChunk(doc, current);
      if (next !== -1) seekToChunk(next);
      return;
    }
    // Back: to the start of this paragraph, or the previous one if already
    // at its start.
    seekToChunk(previousBlockChunk(doc, current));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- uses refs only
  }, [seekToChunk]);

  const skipChunk = useCallback((delta: 1 | -1) => {
    seekToChunk(Math.max(0, indexRef.current) + delta);
  }, [seekToChunk]);

  /** Start reading at the paragraph containing `node` (tap to seek). */
  const seekToNode = useCallback((node: Node) => {
    const root = getContentRoot();
    if (!root) return false;
    const block = blockIndexOf(root, node);
    if (block === -1) return false;
    const doc = docRef.current ?? ensureDocument();
    if (!doc) return false;
    const chunk = doc.blockFirstChunk[block];
    if (chunk === -1) return false;
    if (statusRef.current === 'playing') seekToChunk(chunk);
    else begin(chunk);
    return true;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- uses refs only
  }, [seekToChunk]);

  /** Close the player and stop reading. */
  const close = useCallback(() => {
    haltOutput();
    clearPrefetch();
    clearHighlight();
    stopKeepAlive();
    releaseWakeLock();
    autoplayPendingRef.current = false;
    pausedRef.current = false;
    indexRef.current = -1;
    setChunkIndex(-1);
    setDownload(null);
    setSleepTimer({ mode: 'off' });
    setStatus('idle');
    setOpen(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- uses refs only
  }, []);

  /** Open the bar and start reading (toolbar button). */
  const start = useCallback(() => {
    if (statusRef.current === 'playing') return;
    play();
  }, [play]);

  const confirmDownload = useCallback(() => {
    const voice = neuralVoiceRef.current;
    if (!voice) return;
    confirmedDownloadsRef.current.add(voice.id);
    begin(indexRef.current >= 0 ? indexRef.current : undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- uses refs only
  }, []);

  /** Read with device voices for the rest of this session. */
  const switchToDeviceVoices = useCallback(() => {
    haltOutput();
    setErrorKind(null);
    // The voice-change effect restarts reading once the engine has switched.
    setStatus('preparing');
    setNeuralFallback(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- uses refs only
  }, []);

  /** Switch the saved engine to HD voices (when no device voice exists). */
  const switchToHdVoices = useCallback(() => {
    argsRef.current.onPrefChange('ttsEngine', 'neural');
    setNeuralFallback(false);
    setErrorKind(null);
    setStatus('idle');
  }, [setStatus]);

  // ------------------------------------------------------------------------
  // Effects
  // ------------------------------------------------------------------------

  // Chapter change: stop the old text; continue on the new chapter if we were
  // reading (auto "next chapter" or manual navigation while playing).
  useEffect(() => {
    const wasReading = statusRef.current === 'playing' || statusRef.current === 'preparing';
    haltOutput();
    invalidateDocument();
    indexRef.current = -1;
    setChunkIndex(-1);
    if (!chapterKey) {
      if (wasReading && open) {
        autoplayPendingRef.current = true;
        setStatus('preparing');
      }
      return;
    }
    if (!open) return;
    if (autoplayPendingRef.current || wasReading) {
      autoplayPendingRef.current = false;
      // Let the reader render and restore its scroll position first.
      const id = requestAnimationFrame(() => begin(0));
      return () => cancelAnimationFrame(id);
    }
    if (statusRef.current !== 'needsDownload' && statusRef.current !== 'error') setStatus('idle');
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only the chapter identity matters
  }, [chapterKey]);

  // Text-affecting preferences: rebuild the chunks, keep the position.
  useEffect(() => {
    if (!docRef.current) return;
    const doc = docRef.current;
    const block = doc.chunks[indexRef.current]?.block;
    const wasPlaying = statusRef.current === 'playing';
    haltOutput();
    invalidateDocument();
    const fresh = ensureDocument();
    if (!fresh) return;
    const idx = block === undefined ? -1 : Math.max(0, fresh.chunks.findIndex(c => c.block === block));
    indexRef.current = idx;
    setChunkIndex(idx);
    if (wasPlaying) runFrom(Math.max(0, idx));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- rebuild only on these inputs
  }, [prefs.ttsSkipNotes, prefs.ttsReadTitle, lang]);

  // Voice / engine change: restart the current sentence with the new voice.
  const voiceKey = engine === 'neural'
    ? `${neuralVoice?.id}|${neuralOptionsKey(neuralOptions(prefs))}`
    : `browser|${prefs.ttsBrowserVoices[lang] ?? ''}|${prefs.ttsPitch}`;
  useEffect(() => {
    const s = statusRef.current;
    // Also halt when paused: the loaded sentence was made with the old voice.
    // Resume then restarts the sentence.
    if (s !== 'idle') haltOutput();
    clearPrefetch();
    if (s === 'playing' || s === 'preparing' || s === 'needsDownload' || s === 'error') {
      if (s === 'playing' || s === 'preparing') begin(indexRef.current >= 0 ? indexRef.current : undefined);
      else setStatus(open ? 'idle' : s);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- restart only when the voice changes
  }, [voiceKey]);

  // Speed applies immediately to HD audio (device voices: next sentence).
  // Volume is baked into each HD sentence; where the browser honours
  // `audio.volume` (not iOS), lowering it also applies to the current one.
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.playbackRate = prefs.ttsRate;
      const baked = bakedVolumeRef.current;
      audioRef.current.volume = baked > 0 ? Math.min(1, prefs.ttsVolume / baked) : 1;
    }
  }, [prefs.ttsRate, prefs.ttsVolume]);

  // Highlight mode / colors.
  useEffect(() => {
    ensureHighlightStyle(highlightColors.block, highlightColors.sentence);
  }, [highlightColors.block, highlightColors.sentence]);
  useEffect(() => {
    if (indexRef.current >= 0 && (statusRef.current === 'playing' || statusRef.current === 'paused')) {
      showChunk(indexRef.current);
    } else {
      clearHighlight();
    }
     
  }, [prefs.ttsHighlight]);

  // Pause auto-scroll while the user scrolls by hand.
  useEffect(() => {
    if (!open) return;
    const mark = () => { userScrollAtRef.current = Date.now(); };
    const onKey = (e: KeyboardEvent) => {
      if (['PageUp', 'PageDown', 'ArrowUp', 'ArrowDown', 'Home', 'End', ' '].includes(e.key)) mark();
    };
    window.addEventListener('wheel', mark, { passive: true });
    window.addEventListener('touchmove', mark, { passive: true });
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('wheel', mark);
      window.removeEventListener('touchmove', mark);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  // Re-acquire the wake lock when coming back to the tab.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible' && statusRef.current === 'playing') acquireWakeLock();
    };
    // Backgrounded: the neural chain keeps running from the audio element's
    // ended event, so just make sure the element is still playing.
    const onHidden = () => {
      if (document.visibilityState !== 'hidden' || statusRef.current !== 'playing') return;
      if (engineRef.current !== 'neural' || pausedRef.current) return;
      const audio = audioRef.current;
      if (audio && audio.paused && audio.src) audio.play().catch(() => undefined);
    };
    document.addEventListener('visibilitychange', onVisible);
    document.addEventListener('visibilitychange', onHidden);
    return () => {
      document.removeEventListener('visibilitychange', onVisible);
      document.removeEventListener('visibilitychange', onHidden);
    };
     
    // eslint-disable-next-line react-hooks/exhaustive-deps -- wake lock helpers use refs only
  }, []);
  useEffect(() => {
    if (!prefs.ttsKeepScreenOn) releaseWakeLock();
    else if (statusRef.current === 'playing') acquireWakeLock();
     
    // eslint-disable-next-line react-hooks/exhaustive-deps -- wake lock helpers use refs only
  }, [prefs.ttsKeepScreenOn]);

  // Sleep timer (time based; "end of chapter" is handled by the loop).
  useEffect(() => {
    if (sleepTimer.mode !== 'time') return;
    const id = window.setTimeout(() => {
      pause();
      setSleepTimer({ mode: 'off' });
    }, Math.max(0, sleepTimer.endsAt - Date.now()));
    return () => window.clearTimeout(id);
  }, [sleepTimer, pause]);

  // Media Session: lock screen / headset / keyboard media keys.
  useEffect(() => {
    const ms = navigator.mediaSession;
    if (!ms || !open) return;
    ms.metadata = new MediaMetadata({
      title: chapterTitle,
      artist: novelTitle,
      artwork: artwork ? [{ src: artwork, sizes: '512x512' }] : [],
    });
    const handlers: [MediaSessionAction, MediaSessionActionHandler][] = [
      ['play', () => play()],
      ['pause', () => pause()],
      ['stop', () => close()],
      ['previoustrack', () => skipBlock(-1)],
      ['nexttrack', () => skipBlock(1)],
      ['seekbackward', () => skipChunk(-1)],
      ['seekforward', () => skipChunk(1)],
    ];
    handlers.forEach(([action, handler]) => {
      try { ms.setActionHandler(action, handler); } catch { /* unsupported action */ }
    });
    return () => {
      handlers.forEach(([action]) => {
        try { ms.setActionHandler(action, null); } catch { /* unsupported action */ }
      });
    };
  }, [open, chapterTitle, novelTitle, artwork, play, pause, close, skipBlock, skipChunk]);
  useEffect(() => {
    if (!navigator.mediaSession) return;
    navigator.mediaSession.playbackState = status === 'playing' ? 'playing' : status === 'paused' ? 'paused' : 'none';
  }, [status]);

  // The global audiobook player started: stop reading aloud.
  useEffect(() => {
    const onAudioPlay = () => pause();
    window.addEventListener('lncrawler:audio-play', onAudioPlay);
    return () => window.removeEventListener('lncrawler:audio-play', onAudioPlay);
  }, [pause]);

  // Leaving the reader.
  useEffect(() => () => {
    haltOutput();
    clearPrefetch();
    clearHighlight();
    keepAliveRef.current?.pause();
    releaseWakeLock();
     
    // eslint-disable-next-line react-hooks/exhaustive-deps -- wake lock helpers use refs only
  }, []);

  const blockProgress = blockCount > 0 && blockIndex >= 0 ? (blockIndex + 1) / blockCount : 0;
  const currentBlockNumber = (() => {
    const doc = docRef.current;
    if (!doc || chunkIndex < 0) return 0;
    const block = doc.chunks[chunkIndex]?.block ?? -1;
    if (block < 0) return 0;
    // Count readable paragraphs only (skipped separators aren't numbered).
    return doc.blockFirstChunk.slice(0, block + 1).filter(c => c !== -1).length;
  })();
  const readableBlocks = docRef.current?.blockFirstChunk.filter(c => c !== -1).length ?? 0;

  return {
    open,
    status,
    errorKind,
    errorDetail,
    engine,
    neuralVoice,
    neuralFallback,
    download,
    chunkIndex,
    paragraph: currentBlockNumber,
    paragraphCount: readableBlocks,
    progress: blockProgress,
    sleepTimer,
    setSleepTimer,
    start,
    play,
    pause,
    toggle,
    close,
    skipBlock,
    skipChunk,
    seekToNode,
    confirmDownload,
    switchToDeviceVoices,
    switchToHdVoices,
    /** Readable blocks of the current chapter (for tap to seek). */
    getBlocks: () => {
      const root = getContentRoot();
      return root ? getBlocks(root) : [];
    },
  };
}

export type TtsPlayer = ReturnType<typeof useTtsPlayer>;
