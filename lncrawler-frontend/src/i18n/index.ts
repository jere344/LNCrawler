import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import ICU from 'i18next-icu';
import { availableLanguages } from '@utils/Misc';

// One dynamic import per locale so Vite emits a separate chunk for each and the
// browser only downloads the language actually in use.
const localeLoaders: Record<string, () => Promise<{ default: Record<string, unknown> }>> = {
    en: () => import('./locales/en.json'),
    fr: () => import('./locales/fr.json'),
    es: () => import('./locales/es.json'),
    de: () => import('./locales/de.json'),
    it: () => import('./locales/it.json'),
    ja: () => import('./locales/ja.json'),
    ko: () => import('./locales/ko.json'),
    zh: () => import('./locales/zh.json'),
    pt: () => import('./locales/pt.json'),
    ru: () => import('./locales/ru.json'),
    ar: () => import('./locales/ar.json'),
    hi: () => import('./locales/hi.json'),
    th: () => import('./locales/th.json'),
    vi: () => import('./locales/vi.json'),
    id: () => import('./locales/id.json'),
    tr: () => import('./locales/tr.json'),
    pl: () => import('./locales/pl.json'),
    nl: () => import('./locales/nl.json'),
    sv: () => import('./locales/sv.json'),
    da: () => import('./locales/da.json'),
};

const baseLanguage = (lng: string) => lng.toLowerCase().split('-')[0];

// Minimal i18next backend that resolves a language code to its chunk.
const localeBackend = {
    type: 'backend' as const,
    read(
        language: string,
        _namespace: string,
        callback: (error: unknown, data?: Record<string, unknown> | null) => void,
    ) {
        const loader = localeLoaders[baseLanguage(language)];
        if (!loader) {
            callback(null, null);
            return;
        }
        loader()
            .then((module) => callback(null, module.default))
            .catch((error) => callback(error, null));
    },
};

export const FALLBACK_LANGUAGE = 'en';

// Right-to-left languages, mirrored from the backend registry.
export const RTL_LANGUAGES = ['ar'];

export const isRtl = (code: string): boolean => RTL_LANGUAGES.includes(code);

// Resolves once the detected language (and English fallback) are loaded, so the
// first render isn't a flash of translation keys.
export const i18nReady = i18n
    .use(ICU)
    .use(LanguageDetector)
    .use(initReactI18next)
    .use(localeBackend)
    .init({
        fallbackLng: FALLBACK_LANGUAGE,
        supportedLngs: availableLanguages,
        nonExplicitSupportedLngs: true,
        load: 'languageOnly',
        partialBundledLanguages: true,
        interpolation: {
            // React already escapes interpolated values.
            escapeValue: false,
        },
        detection: {
            // Ordered so a stored choice wins over the browser, which wins over
            // the HTML lang attribute. Key matches LanguageContext's storage.
            order: ['localStorage', 'navigator', 'htmlTag'],
            lookupLocalStorage: 'preferred_ui_language',
            caches: [],
        },
    });

export default i18n;
