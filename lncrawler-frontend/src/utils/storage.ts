// Keys and names below are persisted in users' browsers. Changing a value
// logs everyone out or resets their preferences, so keep them stable.

export const AUTH_TOKEN_KEY = 'authToken';
export const AUTH_USER_KEY = 'user';

// Prefix shared by every reader setting cookie (one cookie per setting).
export const READER_COOKIE_PREFIX = 'lncrawler_reader_';
// Lifetime of the reader setting cookies, in days.
export const READER_COOKIE_DAYS = 365;

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
export const writeLocalStorage = (key: string, value: unknown): void => {
    try {
        localStorage.setItem(key, JSON.stringify(value));
    } catch {
        // ignore quota / disabled storage
    }
};

export const removeLocalStorage = (key: string): void => {
    try {
        localStorage.removeItem(key);
    } catch {
        // ignore disabled storage
    }
};
