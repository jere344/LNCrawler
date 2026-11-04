import { READER_COOKIE_PREFIX, READER_SETTINGS_KEY, readLocalStorage, writeLocalStorage } from '@utils/storage';
import { deleteCookie, getCookie } from '@utils/cookies';
import { defaultSettings } from './readerDefaults';
import { sanitizeSettings, type ReaderSettings } from './readerSettingsSchema';

const STORAGE_VERSION = 1;
const WRITE_DELAY_MS = 300;
// Keys of the old one-cookie-per-setting format, including the key it replaced
const LEGACY_COOKIE_KEYS = [...Object.keys(defaultSettings), 'centerTapToOpenSettings'];

type Listener = () => void;

// null until the first access, which loads the settings
let state: ReaderSettings | null = null;
let writePending = false;
let writeTimer: ReturnType<typeof setTimeout> | undefined;
const listeners = new Set<Listener>();

// Full settings from raw input: every missing or invalid key gets its default
const buildFrom = (raw: unknown): ReaderSettings => ({ ...defaultSettings, ...sanitizeSettings(raw) });

// Defaults for a first load or a reset. Under RTL the swipes swap, so "next" still follows the reading direction.
const baseDefaults = (): ReaderSettings => {
  if (typeof document === 'undefined' || document.documentElement.dir !== 'rtl') return { ...defaultSettings };
  return {
    ...defaultSettings,
    swipeLeftGesture: defaultSettings.swipeRightGesture,
    swipeRightGesture: defaultSettings.swipeLeftGesture,
  };
};

// The `settings` object of a stored payload, or null when there is none
const settingsFrom = (stored: unknown): unknown => {
  const settings = (stored as { settings?: unknown } | null)?.settings;
  return typeof settings === 'object' && settings !== null ? settings : null;
};

const parseJson = (text: string | null): unknown => {
  try {
    return text === null ? null : JSON.parse(text);
  } catch {
    return null;
  }
};

const writeStored = (settings: ReaderSettings): boolean =>
  writeLocalStorage(READER_SETTINGS_KEY, { version: STORAGE_VERSION, settings });

// Old cookies that hold a setting, or null when there are none
const readLegacyCookies = (): Record<string, unknown> | null => {
  const found: Record<string, unknown> = {};
  LEGACY_COOKIE_KEYS.forEach((key) => {
    try {
      const text = getCookie(READER_COOKIE_PREFIX + key);
      if (text === undefined) return;
      found[key] = JSON.parse(text);
    } catch {
      // unreadable cookie: falls back to the default
    }
  });
  return Object.keys(found).length > 0 ? found : null;
};

const load = (): ReaderSettings => {
  const stored = settingsFrom(readLocalStorage<unknown>(READER_SETTINGS_KEY, null));
  if (stored) return buildFrom(stored);

  const legacy = readLegacyCookies();
  if (!legacy) return baseDefaults();
  const migrated = buildFrom(legacy);
  // Cookies go only once the copy is safely in localStorage
  if (writeStored(migrated)) {
    LEGACY_COOKIE_KEYS.forEach((key) => deleteCookie(READER_COOKIE_PREFIX + key));
  }
  return migrated;
};

const notify = (): void => {
  listeners.forEach((listener) => listener());
};

export const flushReaderSettings = (): void => {
  clearTimeout(writeTimer);
  writeTimer = undefined;
  if (!writePending || !state) return;
  writePending = false;
  writeStored(state);
};

// Another tab changed the settings: take its value as-is, without writing it back
const onStorage = (event: StorageEvent): void => {
  if (event.key !== READER_SETTINGS_KEY) return;
  clearTimeout(writeTimer);
  writePending = false;
  state = buildFrom(settingsFrom(parseJson(event.newValue)));
  notify();
};

// Listeners are added once, on first load
const install = (): void => {
  if (typeof window === 'undefined') return;
  window.addEventListener('pagehide', flushReaderSettings);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushReaderSettings();
  });
  window.addEventListener('storage', onStorage);
};

const getState = (): ReaderSettings => {
  if (!state) {
    state = load();
    install();
  }
  return state;
};

// Every change gets a new object (useSyncExternalStore compares by identity) and a debounced write
const setState = (next: ReaderSettings): void => {
  state = next;
  writePending = true;
  clearTimeout(writeTimer);
  writeTimer = setTimeout(flushReaderSettings, WRITE_DELAY_MS);
  notify();
};

export const getReaderSettings = (): ReaderSettings => getState();

export const subscribeReaderSettings = (listener: Listener): (() => void) => {
  getState();
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export const updateReaderSetting = <K extends keyof ReaderSettings>(key: K, value: ReaderSettings[K]): void => {
  setState({ ...getState(), [key]: value });
};

export const replaceReaderSettings = (next: ReaderSettings): void => {
  setState({ ...next });
};

export const resetReaderSettings = (): void => {
  setState(baseDefaults());
};
