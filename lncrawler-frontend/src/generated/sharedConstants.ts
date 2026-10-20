// generated — do not edit, run npm run constants:sync
// Source: lncrawler-api/lncrawler_api/shared_constants.json

export const LANGUAGE_CODES = [
    'en',
    'fr',
    'es',
    'de',
    'it',
    'ja',
    'ko',
    'zh',
    'pt',
    'ru',
    'ar',
    'hi',
    'th',
    'vi',
    'id',
    'tr',
    'pl',
    'nl',
    'sv',
    'da',
] as const;
export type LanguageCode = typeof LANGUAGE_CODES[number];

export const RTL_LANGUAGES = [
    'ar',
] as const;

export const NOVEL_SORTS = [
    'title',
    'rating',
    'date_added',
    'popularity',
    'trending',
    'last_updated',
] as const;
export type NovelSort = typeof NOVEL_SORTS[number];
