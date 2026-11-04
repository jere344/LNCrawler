import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { READER_COOKIE_PREFIX, READER_SETTINGS_KEY } from '@utils/storage';
import { deleteCookie } from '@utils/cookies';
import { defaultSettings } from './readerDefaults';

type Store = typeof import('./readerSettingsStore');

const setCookie = (name: string, value: string): void => {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/`;
};

const clearCookies = (): void => {
  document.cookie.split('; ').filter(Boolean).forEach((row) => deleteCookie(row.split('=')[0]));
};

const storedValue = (): unknown => JSON.parse(localStorage.getItem(READER_SETTINGS_KEY) ?? 'null');

// Each test gets a fresh module, so its in-memory state starts empty
let store: Store;

beforeEach(async () => {
  localStorage.clear();
  clearCookies();
  vi.useFakeTimers();
  vi.resetModules();
  store = await import('./readerSettingsStore');
});

afterEach(() => {
  // Pending timers of an old module instance must never fire into a later test
  vi.useRealTimers();
  vi.restoreAllMocks();
  localStorage.clear();
  clearCookies();
});

describe('migration from cookies', () => {
  it('copies the cookies into localStorage, then deletes them', () => {
    setCookie(READER_COOKIE_PREFIX + 'fontSize', JSON.stringify(20));
    setCookie(READER_COOKIE_PREFIX + 'centerTapToOpenSettings', JSON.stringify(false));

    expect(store.getReaderSettings().fontSize).toBe(20);
    expect(store.getReaderSettings().controlsTrigger).toBe('off');
    expect(storedValue()).toEqual({
      version: 1,
      settings: expect.objectContaining({ fontSize: 20, controlsTrigger: 'off' }),
    });
    expect(document.cookie).not.toContain(READER_COOKIE_PREFIX);
  });

  it('keeps the cookies when localStorage cannot be written', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota');
    });
    setCookie(READER_COOKIE_PREFIX + 'fontSize', JSON.stringify(20));

    expect(store.getReaderSettings().fontSize).toBe(20);
    expect(document.cookie).toContain(READER_COOKIE_PREFIX + 'fontSize=');
  });

  it('prefers the localStorage value over the cookies', () => {
    localStorage.setItem(READER_SETTINGS_KEY, JSON.stringify({ version: 1, settings: { fontSize: 30 } }));
    setCookie(READER_COOKIE_PREFIX + 'fontSize', JSON.stringify(20));

    expect(store.getReaderSettings().fontSize).toBe(30);
  });

  it('falls back to the cookies when the localStorage value is corrupt', () => {
    localStorage.setItem(READER_SETTINGS_KEY, '{not json');
    setCookie(READER_COOKIE_PREFIX + 'fontSize', JSON.stringify(20));

    expect(store.getReaderSettings().fontSize).toBe(20);
  });

  it('a malformed cookie falls back to the default without throwing', () => {
    // A raw '%' makes decodeURIComponent throw inside getCookie
    document.cookie = `${READER_COOKIE_PREFIX}fontSize=%E0%A4%A; path=/`;
    setCookie(READER_COOKIE_PREFIX + 'margin', JSON.stringify(4));

    expect(() => store.getReaderSettings()).not.toThrow();
    expect(store.getReaderSettings().fontSize).toBe(defaultSettings.fontSize);
    expect(store.getReaderSettings().margin).toBe(4);
  });
});

describe('writes', () => {
  it('debounces updates into a single write', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    store.getReaderSettings();

    store.updateReaderSetting('fontSize', 22);
    store.updateReaderSetting('fontSize', 24);
    expect(setItem).not.toHaveBeenCalledWith(READER_SETTINGS_KEY, expect.anything());

    vi.advanceTimersByTime(299);
    expect(setItem).not.toHaveBeenCalledWith(READER_SETTINGS_KEY, expect.anything());

    vi.advanceTimersByTime(1);
    const writes = setItem.mock.calls.filter(([key]) => key === READER_SETTINGS_KEY);
    expect(writes).toHaveLength(1);
    expect(storedValue()).toEqual({ version: 1, settings: expect.objectContaining({ fontSize: 24 }) });
  });

  it('flush writes at once', () => {
    store.getReaderSettings();
    store.updateReaderSetting('fontSize', 26);

    store.flushReaderSettings();
    expect(storedValue()).toEqual({ version: 1, settings: expect.objectContaining({ fontSize: 26 }) });
  });
});

describe('subscriptions', () => {
  it('notifies listeners and gives a new object on update', () => {
    const listener = vi.fn();
    const before = store.getReaderSettings();
    store.subscribeReaderSettings(listener);

    store.updateReaderSetting('fontSize', 18);

    expect(listener).toHaveBeenCalledTimes(1);
    expect(store.getReaderSettings()).not.toBe(before);
    expect(store.getReaderSettings().fontSize).toBe(18);
  });

  it('stops notifying after unsubscribe', () => {
    const listener = vi.fn();
    const unsubscribe = store.subscribeReaderSettings(listener);
    unsubscribe();

    store.updateReaderSetting('fontSize', 18);
    expect(listener).not.toHaveBeenCalled();
  });
});

describe('storage event from another tab', () => {
  it('takes the new value without writing it back', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    store.getReaderSettings();

    window.dispatchEvent(new StorageEvent('storage', {
      key: READER_SETTINGS_KEY,
      newValue: JSON.stringify({ version: 1, settings: { fontSize: 26 } }),
    }));
    expect(store.getReaderSettings().fontSize).toBe(26);

    vi.advanceTimersByTime(1000);
    expect(setItem).not.toHaveBeenCalledWith(READER_SETTINGS_KEY, expect.anything());
  });
});

describe('settings saved before a key existed', () => {
  it('gives the F key its default fullscreen action', () => {
    localStorage.setItem(READER_SETTINGS_KEY, JSON.stringify({ version: 1, settings: { keyD: 'none' } }));

    expect(store.getReaderSettings().keyF).toBe('fullscreen');
    expect(store.getReaderSettings().keyD).toBe('none');
  });
});

describe('narrated engine saved before the audiobook preference', () => {
  it('reads it as the audiobook preference with the default engine', () => {
    localStorage.setItem(READER_SETTINGS_KEY, JSON.stringify({ version: 1, settings: { ttsEngine: 'narrated' } }));

    expect(store.getReaderSettings().ttsPreferAudiobook).toBe(true);
    expect(store.getReaderSettings().ttsEngine).toBe('browser');
  });

  it('defaults the audiobook preference to off', () => {
    expect(store.getReaderSettings().ttsPreferAudiobook).toBe(false);
  });
});

describe('reset', () => {
  it('returns every setting to its default', () => {
    store.updateReaderSetting('fontSize', 30);

    store.resetReaderSettings();
    expect(store.getReaderSettings()).toEqual(defaultSettings);
  });
});

describe('defaults under RTL', () => {
  beforeEach(() => {
    document.documentElement.dir = 'rtl';
  });

  afterEach(() => {
    document.documentElement.removeAttribute('dir');
  });

  it('swaps the swipe gestures on a first load, so next still follows the reading direction', () => {
    expect(store.getReaderSettings().swipeLeftGesture).toBe(defaultSettings.swipeRightGesture);
    expect(store.getReaderSettings().swipeRightGesture).toBe(defaultSettings.swipeLeftGesture);
  });

  it('swaps the swipe gestures again on reset', () => {
    store.updateReaderSetting('swipeLeftGesture', 'nextChapter');

    store.resetReaderSettings();
    expect(store.getReaderSettings().swipeLeftGesture).toBe(defaultSettings.swipeRightGesture);
  });

  it('keeps a swipe choice that is already stored', () => {
    localStorage.setItem(READER_SETTINGS_KEY, JSON.stringify({ version: 1, settings: { swipeLeftGesture: 'nextChapter' } }));

    expect(store.getReaderSettings().swipeLeftGesture).toBe('nextChapter');
  });

  it('keeps the LTR swipes when the page is not RTL', () => {
    document.documentElement.removeAttribute('dir');

    expect(store.getReaderSettings().swipeLeftGesture).toBe(defaultSettings.swipeLeftGesture);
  });
});
