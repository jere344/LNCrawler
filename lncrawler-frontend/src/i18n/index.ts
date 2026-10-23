import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import ICU from 'i18next-icu';
import { availableLanguages } from '@utils/Misc';
import { RTL_LANGUAGES } from '../generated/sharedConstants';

// One chunk per locale so the browser only downloads the language in use.
// Keys are derived from the filenames, so adding a locale needs no edit here.
type LocaleModule = () => Promise<{ default: Record<string, unknown> }>;
const localeLoaders: Record<string, LocaleModule> = Object.fromEntries(
    Object.entries(import.meta.glob('./locales/*.json') as Record<string, LocaleModule>).map(
        ([path, load]) => [path.slice(path.lastIndexOf('/') + 1, -'.json'.length), load],
    ),
);

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

const FALLBACK_LANGUAGE = 'en';

export const isRtl = (code: string): boolean => (RTL_LANGUAGES as readonly string[]).includes(code);

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
