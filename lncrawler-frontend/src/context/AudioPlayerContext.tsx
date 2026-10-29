import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { matchPath, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { audiobookService } from '@services/api';
import type { AudiobookChapter, AudiobookDetail, ListeningProgress } from '@models/audiobook_types';
import { PROGRESS_KEY, progressKey, readLocalProgress } from '@utils/audiobook';
import { readLocalStorage, writeLocalStorage } from '@utils/storage';
import { useAuth } from './AuthContext';
import { useNotification } from './NotificationContext';

export type AudioStatus = 'idle' | 'loading' | 'playing' | 'paused' | 'error';

export type SleepState = { type: 'chapterEnd' } | { type: 'time'; endsAt: number };

export type SleepOption = { type: 'chapterEnd' } | { type: 'time'; minutes: number };

export interface PlayOptions {
  chapterId?: number;
  position?: number;
  detail?: AudiobookDetail;
}

export interface AudioPlayerValue {
  book: AudiobookDetail | null;
  // Available chapters of all available parts, in order.
  queue: AudiobookChapter[];
  index: number;
  chapter: AudiobookChapter | null;
  status: AudioStatus;
  speed: number;
  sleep: SleepState | null;
  expanded: boolean;
  suppressed: boolean;
  // Height of the mini bar in px, 0 when it is hidden. Pages add it as bottom padding.
  barHeight: number;
  // Resolves to false (after a toast) when nothing could be started, so callers can fall back.
  playAudiobook: (slug: string, lang: string, opts?: PlayOptions) => Promise<boolean>;
  // Retries when the last load failed.
  toggle: () => void;
  pause: () => void;
  seekTo: (seconds: number) => void;
  skip: (delta: number) => void;
  next: () => void;
  prev: () => void;
  playChapter: (index: number) => void;
  setSpeed: (speed: number) => void;
  setSleep: (option: SleepOption | null) => void;
  close: () => void;
  expand: (open: boolean) => void;
  // Hides the mini bar while another reader surface (the TTS bar) is open.
  setSuppressed: (suppressed: boolean) => void;
}

// Updates about 4 times a second: kept out of AudioPlayerValue so that only the time displays re-render.
export interface AudioPlayerTimeValue {
  position: number;
  duration: number;
}

// The handlers of AudioPlayerValue that the provider keeps at a stable identity.
type Handlers = Pick<
  AudioPlayerValue,
  'playAudiobook' | 'toggle' | 'pause' | 'seekTo' | 'skip' | 'next' | 'prev' | 'playChapter' | 'setSpeed' | 'setSleep' | 'close'
>;

// Handlers shared by the audio element listeners, the timers and the keyboard, which outlive a render.
interface Actions {
  play: () => void;
  pause: () => void;
  toggle: () => void;
  seekTo: (seconds: number) => void;
  skip: (delta: number) => void;
  next: () => void;
  prev: () => void;
  playChapter: (index: number) => void;
  setSpeed: (speed: number) => void;
  close: () => void;
  preloadNext: () => void;
  onLoaded: () => void;
  onPlaying: () => void;
  onPause: () => void;
  onTimeUpdate: () => void;
  onEnded: () => void;
  onError: () => void;
  onDurationChange: () => void;
  onSeeked: () => void;
  onWaiting: () => void;
  onHide: () => void;
  onTtsPlay: () => void;
  reportListening: () => void;
  persistProgress: (finished: boolean, onHide?: boolean) => void;
}

const AudioPlayerContext = createContext<AudioPlayerValue | null>(null);
const AudioPlayerTimeContext = createContext<AudioPlayerTimeValue | null>(null);

export const useAudioPlayer = (): AudioPlayerValue => {
  const value = useContext(AudioPlayerContext);
  if (!value) throw new Error('useAudioPlayer must be used inside AudioPlayerProvider');
  return value;
};

// Only for the components that display the position (the mini bar and the full player).
export const useAudioPlayerTime = (): AudioPlayerTimeValue => {
  const value = useContext(AudioPlayerTimeContext);
  if (!value) throw new Error('useAudioPlayerTime must be used inside AudioPlayerProvider');
  return value;
};

const MINI_BAR_HEIGHT = 64;
const SPEED_MIN = 0.75;
const SPEED_MAX = 2.5;
const SPEED_STEP = 0.25;
const SAVE_INTERVAL_MS = 15_000;
const PLAY_REPORT_S = 120;
// Listening time left over when a chapter ends is reported only from this length on.
const MIN_LISTEN_REPORT_S = 5;
const PREFETCH_BEFORE_END_S = 30;
const SLEEP_FADE_MS = 5_000;
const SEEK_BACK_S = 15;
const SEEK_FORWARD_S = 30;
const SYNCED_FOR_KEY = 'audiobookProgressSyncedFor';
const PROGRESS_LIMIT = 50;
const READER_ROUTE = '/novels/:novelSlug/:sourceSlug/chapter/:chapterNumber';
// Window events shared with components/reader/tts/useTtsPlayer.ts: only one of the two audio sources plays.
const AUDIO_PLAY_EVENT = 'lncrawler:audio-play';
const TTS_PLAY_EVENT = 'lncrawler:tts-play';
// A 25 ms silent WAV (8 kHz, 8-bit mono), used to unlock the element for autoplay.
const SILENT_WAV = 'data:audio/wav;base64,UklGRuwAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YcgAAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgA==';

interface SavedPosition {
  chapter_id: number;
  position_s: number;
  speed: number;
  finished: boolean;
  updated_at: string;
}

type SavedPositions = Record<string, SavedPosition>;

type Resume = Pick<ListeningProgress, 'chapter_id' | 'position_s' | 'finished'> & { speed?: number };

const clampSpeed = (value: number): number =>
  Math.min(SPEED_MAX, Math.max(SPEED_MIN, Math.round(value / SPEED_STEP) * SPEED_STEP));

const queueOf = (detail: AudiobookDetail): AudiobookChapter[] =>
  detail.parts.filter((part) => part.state === 'available').flatMap((part) => part.chapters ?? []);

// Object key order is insertion order: re-inserting a key makes it the newest, so the oldest go first.
const writeSavedPosition = (key: string, entry: SavedPosition) => {
  const map = readLocalStorage<SavedPositions>(PROGRESS_KEY, {});
  delete map[key];
  map[key] = entry;
  const keys = Object.keys(map);
  keys.slice(0, Math.max(0, keys.length - PROGRESS_LIMIT)).forEach((oldKey) => delete map[oldKey]);
  writeLocalStorage(PROGRESS_KEY, map);
};

// Local positions written while logged out go to the server on login, where the server has none or an older one.
const pushIfNewer = async (slug: string, lang: string, entry: SavedPosition) => {
  try {
    const server = await audiobookService.getProgress(slug, lang);
    if (server?.updated_at && Date.parse(server.updated_at) >= Date.parse(entry.updated_at)) return;
    await audiobookService.saveProgress(slug, lang, {
      chapter_id: entry.chapter_id,
      position_s: entry.position_s,
      speed: entry.speed,
      finished: entry.finished,
    });
  } catch {
    // best effort: the next save catches up
  }
};

const syncLocalProgress = () => {
  const local = readLocalStorage<SavedPositions>(PROGRESS_KEY, {});
  Object.entries(local).forEach(([key, entry]) => {
    const [slug, lang] = key.split('|');
    void pushIfNewer(slug, lang, entry);
  });
};

export function AudioPlayerProvider({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  const { notify } = useNotification();
  const { isAuthenticated, user } = useAuth();
  const userId = user?.id ?? null;
  const { pathname } = useLocation();
  const onReaderRoute = matchPath(READER_ROUTE, pathname) !== null;

  // One element for the whole app.
  const [audio] = useState(() => new Audio());
  const [book, setBook] = useState<AudiobookDetail | null>(null);
  const [queue, setQueue] = useState<AudiobookChapter[]>([]);
  const [index, setIndex] = useState(-1);
  const [status, setStatus] = useState<AudioStatus>('idle');
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [speed, setSpeedState] = useState(1);
  const [sleep, setSleepState] = useState<SleepState | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [suppressed, setSuppressedState] = useState(false);

  // Latest values for handlers that outlive a render (audio events, timers, keys).
  const live = useRef({ book, queue, index, speed, sleep, status, position, duration, isAuthenticated });
  live.current = { book, queue, index, speed, sleep, status, position, duration, isAuthenticated };
  // Every handler below, refreshed each render; the listeners call through it.
  const actionsRef = useRef<Actions | null>(null);

  const pendingSeekRef = useRef(0);
  const autoplayRef = useRef(false);
  // Pause events that come with a source switch are not progress.
  const suppressPauseRef = useRef(false);
  const lastTimeRef = useRef(0);
  const listenedRef = useRef(0);
  const countedRef = useRef(new Set<number>());
  const preloadRef = useRef<HTMLAudioElement | null>(null);
  const previousAuthRef = useRef(isAuthenticated);

  const persistProgress = (finished: boolean, onHide = false) => {
    const current = live.current;
    const chapter = current.queue[current.index];
    if (!current.book || !chapter) return;
    const body = {
      chapter_id: chapter.chapter_id,
      position_s: audio.readyState >= 1 ? audio.currentTime : pendingSeekRef.current,
      speed: current.speed,
      finished,
    };
    const { slug, language } = current.book;
    writeSavedPosition(progressKey(slug, language), { ...body, updated_at: new Date().toISOString() });
    if (!current.isAuthenticated) return;
    if (onHide) {
      audiobookService.saveProgressOnHide(slug, language, body);
    } else {
      audiobookService.saveProgress(slug, language, body).catch(() => undefined);
    }
  };

  const reportListening = () => {
    const current = live.current;
    const chapter = current.queue[current.index];
    const seconds = Math.round(listenedRef.current);
    listenedRef.current = 0;
    if (!current.book || !chapter || seconds <= 0) return;
    void audiobookService.play(current.book.slug, current.book.language, {
      chapter_id: chapter.chapter_id,
      listened_s: seconds,
    });
  };

  const loadChapter = (items: AudiobookChapter[], i: number, at: number, autoplay: boolean) => {
    const chapter = items[i];
    if (!chapter) return;
    // Save the chapter being left, before its source is replaced.
    if (live.current.book && live.current.index >= 0) persistProgress(false);
    // The listening time counts per chapter: the pending chunk goes to the chapter being left, then the count restarts.
    if (listenedRef.current >= MIN_LISTEN_REPORT_S) reportListening();
    listenedRef.current = 0;
    pendingSeekRef.current = at;
    autoplayRef.current = autoplay;
    suppressPauseRef.current = true;
    lastTimeRef.current = 0;
    audio.src = chapter.audio_url;
    audio.playbackRate = live.current.speed;
    audio.preservesPitch = true;
    setQueue(items);
    setIndex(i);
    setPosition(at);
    setDuration(chapter.duration_s);
    setStatus('loading');
  };

  const startAt = (items: AudiobookChapter[], chapterId: number, at: number) => {
    const found = items.findIndex((chapter) => chapter.chapter_id === chapterId);
    // A chapter that is not in the queue starts the book over, at its beginning.
    if (found < 0) return { index: 0, position: 0 };
    return { index: found, position: at };
  };

  // Logged in: the progress that came with the detail. Logged out: this browser's saved position.
  const savedProgress = (detail: AudiobookDetail): Resume | null =>
    live.current.isAuthenticated ? detail.progress : readLocalProgress(detail.slug, detail.language);

  const resumePoint = (detail: AudiobookDetail, items: AudiobookChapter[]) => {
    const saved = savedProgress(detail);
    if (!saved || saved.finished || saved.chapter_id === null) return { index: 0, position: 0 };
    return startAt(items, saved.chapter_id, saved.position_s);
  };

  // Runs first in a user action, before any await: iOS/Safari only let an element play inside the gesture, and the
  // fetch in between would lose it. A fresh element (no source yet) plays the silent WAV, which the real source
  // replaces later. An element that already has a source has played from a gesture before, so it is left alone.
  // The play is only there to unlock: its outcome is ignored, and the silent WAV is paused once it has finished.
  const unlockAudio = () => {
    if (audio.getAttribute('src')) return;
    audio.src = SILENT_WAV;
    const release = () => {
      if (audio.getAttribute('src') === SILENT_WAV) audio.pause();
    };
    audio.play().then(release, release);
  };

  const playAudiobook = async (slug: string, lang: string, opts: PlayOptions = {}): Promise<boolean> => {
    unlockAudio();
    try {
      const detail = opts.detail ?? (await audiobookService.detail(slug, lang));
      const items = queueOf(detail);
      if (items.length === 0) {
        notify({ message: t('audioPlayer.noAudio'), severity: 'info' });
        return false;
      }
      const start = opts.chapterId !== undefined
        ? startAt(items, opts.chapterId, opts.position ?? 0)
        : resumePoint(detail, items);
      // The speed listened at last time comes back with the book
      const savedSpeed = savedProgress(detail)?.speed;
      if (savedSpeed) setSpeed(savedSpeed);
      setBook(detail);
      loadChapter(items, start.index, start.position, true);
      return true;
    } catch {
      notify({ message: t('audioPlayer.loadError'), severity: 'error' });
      return false;
    }
  };

  const play = () => {
    const current = live.current;
    if (current.index < 0) return;
    if (current.status === 'error') {
      loadChapter(current.queue, current.index, current.position, true);
      return;
    }
    if (audio.ended) audio.currentTime = 0;
    audio.play().catch(() => {
      setStatus((prev) => (prev === 'error' ? prev : 'paused'));
    });
  };

  const pause = () => {
    audio.pause();
  };

  const toggle = () => {
    if (live.current.status === 'error' || audio.paused) {
      play();
    } else {
      pause();
    }
  };

  const seekTo = (seconds: number) => {
    if (live.current.index < 0) return;
    const max = Number.isFinite(audio.duration) ? audio.duration : live.current.duration;
    const target = Math.min(Math.max(seconds, 0), max || 0);
    audio.currentTime = target;
    lastTimeRef.current = target;
    setPosition(target);
  };

  const skip = (delta: number) => seekTo(audio.currentTime + delta);

  const playChapter = (i: number) => {
    const current = live.current;
    if (i < 0 || i >= current.queue.length) return;
    loadChapter(current.queue, i, 0, true);
  };

  const next = () => {
    const current = live.current;
    if (current.index >= current.queue.length - 1) return;
    playChapter(current.index + 1);
  };

  const prev = () => {
    const current = live.current;
    if (audio.currentTime > 3 || current.index <= 0) {
      seekTo(0);
    } else {
      playChapter(current.index - 1);
    }
  };

  const setSpeed = (value: number) => {
    const next = clampSpeed(value);
    setSpeedState(next);
    // loadChapter reads the ref, which a render would only update later
    live.current.speed = next;
    audio.playbackRate = next;
    audio.preservesPitch = true;
  };

  const setSleep = (option: SleepOption | null) => {
    if (option === null) {
      setSleepState(null);
    } else if (option.type === 'chapterEnd') {
      setSleepState({ type: 'chapterEnd' });
    } else {
      setSleepState({ type: 'time', endsAt: Date.now() + option.minutes * 60_000 });
    }
  };

  const close = () => {
    persistProgress(false);
    pendingSeekRef.current = 0;
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
    // Release the preloaded chapter too, so its download stops.
    if (preloadRef.current) {
      preloadRef.current.pause();
      preloadRef.current.removeAttribute('src');
      preloadRef.current.load();
      preloadRef.current = null;
    }
    setBook(null);
    setQueue([]);
    setIndex(-1);
    setStatus('idle');
    setPosition(0);
    setDuration(0);
    setSleepState(null);
    setExpanded(false);
  };

  const preloadNext = () => {
    const current = live.current;
    const upcoming = current.queue[current.index + 1];
    if (!upcoming || preloadRef.current?.getAttribute('src') === upcoming.audio_url) return;
    const element = new Audio();
    element.preload = 'auto';
    element.src = upcoming.audio_url;
    preloadRef.current = element;
  };

  const onLoaded = () => {
    const at = pendingSeekRef.current;
    pendingSeekRef.current = 0;
    suppressPauseRef.current = false;
    if (at > 0) {
      audio.currentTime = at;
      lastTimeRef.current = at;
    }
    setDuration(Number.isFinite(audio.duration) ? audio.duration : 0);
    if (autoplayRef.current) {
      autoplayRef.current = false;
      play();
    } else {
      setStatus('paused');
    }
  };

  const onPlaying = () => {
    const current = live.current;
    if (!current.book) return;
    setStatus('playing');
    window.dispatchEvent(new Event(AUDIO_PLAY_EVENT));
    const chapter = current.queue[current.index];
    // A play is counted once per chapter and session, when the chapter starts.
    if (chapter && !countedRef.current.has(chapter.chapter_id)) {
      countedRef.current.add(chapter.chapter_id);
      void audiobookService.play(current.book.slug, current.book.language, { chapter_id: chapter.chapter_id });
    }
  };

  const onPause = () => {
    if (!live.current.book || audio.ended || suppressPauseRef.current) return;
    setStatus((prev) => (prev === 'error' ? prev : 'paused'));
    persistProgress(false);
  };

  const onTimeUpdate = () => {
    const now = audio.currentTime;
    setPosition(now);
    const delta = now - lastTimeRef.current;
    lastTimeRef.current = now;
    // Only real playback counts: a seek or a throttled timer shows up as a jump, not a small step.
    if (!audio.paused && delta > 0 && delta < 5) listenedRef.current += delta;
    if (listenedRef.current >= PLAY_REPORT_S) reportListening();
    if (Number.isFinite(audio.duration) && audio.duration - now <= PREFETCH_BEFORE_END_S) preloadNext();
  };

  const onEnded = () => {
    const current = live.current;
    if (!current.book) return;
    const last = current.index >= current.queue.length - 1;
    persistProgress(last);
    if (current.sleep?.type === 'chapterEnd') {
      setSleepState(null);
      setStatus('paused');
      return;
    }
    if (!last) {
      loadChapter(current.queue, current.index + 1, 0, true);
      return;
    }
    setStatus('paused');
  };

  const onError = () => {
    if (!audio.currentSrc || !live.current.book) return;
    suppressPauseRef.current = false;
    pendingSeekRef.current = 0;
    autoplayRef.current = false;
    setStatus('error');
    notify({ message: t('audioPlayer.playbackError'), severity: 'error' });
  };

  const onDurationChange = () => {
    setDuration(Number.isFinite(audio.duration) ? audio.duration : 0);
  };

  const onSeeked = () => {
    lastTimeRef.current = audio.currentTime;
  };

  const onWaiting = () => {
    setStatus((prev) => (prev === 'playing' ? 'loading' : prev));
  };

  const onHide = () => {
    if (document.visibilityState === 'hidden') {
      const current = live.current;
      if (current.book && current.index >= 0) persistProgress(false, true);
    }
  };

  const onTtsPlay = () => {
    pause();
  };

  actionsRef.current = {
    play, pause, toggle, seekTo, skip, next, prev, playChapter, setSpeed, close, preloadNext,
    onLoaded, onPlaying, onPause, onTimeUpdate, onEnded, onError, onDurationChange, onSeeked, onWaiting,
    onHide, onTtsPlay, reportListening, persistProgress,
  };
  const actions = (): Actions => actionsRef.current as Actions;

  // The one audio element's events.
  useEffect(() => {
    const listeners: [string, () => void][] = [
      ['loadedmetadata', () => actions().onLoaded()],
      ['durationchange', () => actions().onDurationChange()],
      ['playing', () => actions().onPlaying()],
      ['waiting', () => actions().onWaiting()],
      ['pause', () => actions().onPause()],
      ['timeupdate', () => actions().onTimeUpdate()],
      ['seeked', () => actions().onSeeked()],
      ['ended', () => actions().onEnded()],
      ['error', () => actions().onError()],
    ];
    listeners.forEach(([event, handler]) => audio.addEventListener(event, handler));
    const onVisibility = () => actions().onHide();
    window.addEventListener('pagehide', onVisibility);
    document.addEventListener('visibilitychange', onVisibility);
    const onTts = () => actions().onTtsPlay();
    window.addEventListener(TTS_PLAY_EVENT, onTts);
    return () => {
      listeners.forEach(([event, handler]) => audio.removeEventListener(event, handler));
      window.removeEventListener('pagehide', onVisibility);
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener(TTS_PLAY_EVENT, onTts);
    };
  }, [audio]);

  // Progress every 15 s while playing.
  useEffect(() => {
    if (status !== 'playing') return;
    const id = window.setInterval(() => actions().persistProgress(false), SAVE_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [status]);

  // Sleep timer: fades the last few seconds, then pauses.
  useEffect(() => {
    if (sleep?.type !== 'time') return;
    const endsAt = sleep.endsAt;
    const id = window.setInterval(() => {
      const remaining = endsAt - Date.now();
      if (remaining <= 0) {
        audio.volume = 1;
        actions().pause();
        setSleepState(null);
        return;
      }
      if (remaining <= SLEEP_FADE_MS) audio.volume = remaining / SLEEP_FADE_MS;
    }, 1000);
    return () => {
      window.clearInterval(id);
      audio.volume = 1;
    };
  }, [sleep, audio]);

  // Logging in pushes the positions saved while logged out, once per account: the flag is cleared on logout.
  useEffect(() => {
    if (!isAuthenticated) {
      if (previousAuthRef.current) localStorage.removeItem(SYNCED_FOR_KEY);
      previousAuthRef.current = false;
      return;
    }
    // The user is not known yet right after the auth check: wait for it.
    if (userId === null) return;
    const justLoggedIn = !previousAuthRef.current;
    previousAuthRef.current = true;
    if (!justLoggedIn || readLocalStorage<string | null>(SYNCED_FOR_KEY, null) === userId) return;
    writeLocalStorage(SYNCED_FOR_KEY, userId);
    syncLocalProgress();
  }, [isAuthenticated, userId]);

  // Lock screen and notification controls.
  useEffect(() => {
    if (!('mediaSession' in navigator)) return;
    const handlers: [MediaSessionAction, (details: MediaSessionActionDetails) => void][] = [
      ['play', () => actions().play()],
      ['pause', () => actions().pause()],
      ['seekbackward', (details) => actions().skip(-(details.seekOffset ?? SEEK_BACK_S))],
      ['seekforward', (details) => actions().skip(details.seekOffset ?? SEEK_FORWARD_S)],
      ['previoustrack', () => actions().prev()],
      ['nexttrack', () => actions().next()],
      ['seekto', (details) => {
        if (details.seekTime !== undefined) actions().seekTo(details.seekTime);
      }],
    ];
    handlers.forEach(([action, handler]) => {
      try {
        navigator.mediaSession.setActionHandler(action, handler);
      } catch {
        // this browser does not support the action
      }
    });
  }, []);

  useEffect(() => {
    if (!('mediaSession' in navigator)) return;
    const chapter = index >= 0 ? queue[index] : undefined;
    if (!book || !chapter) {
      navigator.mediaSession.metadata = null;
      return;
    }
    const artwork: MediaImage[] = [];
    if (book.cover_url) artwork.push({ src: book.cover_url, sizes: '600x600' });
    if (book.cover_jpg_url) artwork.push({ src: book.cover_jpg_url, sizes: '1400x1400' });
    navigator.mediaSession.metadata = new MediaMetadata({
      title: chapter.title,
      artist: book.authors.join(', '),
      album: book.title,
      artwork,
    });
  }, [book, index, queue]);

  useEffect(() => {
    if (!('mediaSession' in navigator)) return;
    navigator.mediaSession.playbackState = status === 'playing' ? 'playing' : status === 'paused' ? 'paused' : 'none';
  }, [status]);

  useEffect(() => {
    if (!('mediaSession' in navigator) || !Number.isFinite(duration) || duration <= 0) return;
    try {
      navigator.mediaSession.setPositionState({
        duration,
        playbackRate: speed,
        position: Math.min(position, duration),
      });
    } catch {
      // position state is optional
    }
  }, [position, duration, speed]);

  // Keyboard controls while the player is open. Never on the reader, which has its own keys.
  useEffect(() => {
    if (!book || suppressed || onReaderRoute) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      // Another handler already used the key, or a dialog, menu, list or slider owns it.
      if (event.defaultPrevented) return;
      const target = event.target as HTMLElement | null;
      if (target && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)) return;
      if (target?.closest('[role="dialog"], [role="menu"], [role="listbox"], [role="slider"]')) return;
      if (document.querySelector('.MuiModal-root:not(.MuiModal-hidden)')) return;
      const current = live.current;
      switch (event.key) {
        case ' ':
          event.preventDefault();
          actions().toggle();
          break;
        case 'ArrowLeft':
          event.preventDefault();
          actions().skip(-SEEK_BACK_S);
          break;
        case 'ArrowRight':
          event.preventDefault();
          actions().skip(SEEK_FORWARD_S);
          break;
        case '[':
          actions().setSpeed(current.speed - SPEED_STEP);
          break;
        case ']':
          actions().setSpeed(current.speed + SPEED_STEP);
          break;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [book, suppressed, onReaderRoute]);

  const chapter = index >= 0 ? queue[index] ?? null : null;

  // The handlers keep one identity and call the closures of the latest render. With the memos below, a consumer
  // re-renders only when what it reads changes, not on every position tick.
  const handlers: Handlers = {
    playAudiobook, toggle, pause, seekTo, skip, next, prev, playChapter, setSpeed, setSleep, close,
  };
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;
  const stable = useMemo<Handlers>(() => ({
    playAudiobook: (...args) => handlersRef.current.playAudiobook(...args),
    toggle: () => handlersRef.current.toggle(),
    pause: () => handlersRef.current.pause(),
    seekTo: (...args) => handlersRef.current.seekTo(...args),
    skip: (...args) => handlersRef.current.skip(...args),
    next: () => handlersRef.current.next(),
    prev: () => handlersRef.current.prev(),
    playChapter: (...args) => handlersRef.current.playChapter(...args),
    setSpeed: (...args) => handlersRef.current.setSpeed(...args),
    setSleep: (...args) => handlersRef.current.setSleep(...args),
    close: () => handlersRef.current.close(),
  }), []);

  const value = useMemo<AudioPlayerValue>(() => ({
    book,
    queue,
    index,
    chapter,
    status,
    speed,
    sleep,
    expanded,
    suppressed,
    barHeight: book && !suppressed ? MINI_BAR_HEIGHT : 0,
    ...stable,
    expand: setExpanded,
    setSuppressed: setSuppressedState,
  }), [book, queue, index, chapter, status, speed, sleep, expanded, suppressed, stable]);

  const time = useMemo<AudioPlayerTimeValue>(() => ({ position, duration }), [position, duration]);

  return (
    <AudioPlayerContext.Provider value={value}>
      <AudioPlayerTimeContext.Provider value={time}>{children}</AudioPlayerTimeContext.Provider>
    </AudioPlayerContext.Provider>
  );
}
