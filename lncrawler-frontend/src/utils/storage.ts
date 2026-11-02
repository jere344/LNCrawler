// Keys and names below are persisted in users' browsers. Changing a value
// logs everyone out or resets their preferences, so keep them stable.

export const AUTH_TOKEN_KEY = 'authToken';
export const AUTH_USER_KEY = 'user';

// Reader settings, stored as one versioned JSON value.
export const READER_SETTINGS_KEY = 'lncrawler_reader_settings';
// Prefix of the old one-cookie-per-setting format. Only read to migrate, never written.
export const READER_COOKIE_PREFIX = 'lncrawler_reader_';

// Reads and parses a JSON value. Falls back when the key is missing or the
// stored text is not valid JSON.
export const readLocalStorage = <T,>(key: string, fallback: T): T => {
    try {
        const raw = localStorage.getItem(key);
        return raw === null ? fallback : (JSON.parse(raw) as T);
    } catch {
        return fallback;
    }
};

// Stores a value as JSON. Storage can be full or disabled, so failures are ignored.
// Returns false when the value was not written.
export const writeLocalStorage = (key: string, value: unknown): boolean => {
    try {
        localStorage.setItem(key, JSON.stringify(value));
        return true;
    } catch {
        // ignore quota / disabled storage
        return false;
    }
};
