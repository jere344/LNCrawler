import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { authService } from '@services/api';
import { availableLanguages } from '@utils/Misc';
import i18n, { isRtl } from '../i18n';

// Keys mirror the backend field names so a profile payload can be spread in.
const UI_LANGUAGE_KEY = 'preferred_ui_language';
const CONTENT_LANGUAGES_KEY = 'preferred_languages';
const LANGUAGE_FILTER_KEY = 'language_filter_enabled';

interface LanguageContextType {
    // Language the interface is displayed in (empty = follow the browser)
    uiLanguage: string;
    // Content languages to segregate the home page by (empty = no segregation)
    contentLanguages: string[];
    // Whether the home page is filtered by content languages at all
    languageFilterEnabled: boolean;
    setUiLanguage: (code: string) => void;
    setContentLanguages: (codes: string[]) => void;
    setLanguageFilterEnabled: (enabled: boolean) => void;
}

const LanguageContext = createContext<LanguageContextType>({
    uiLanguage: '',
    contentLanguages: [],
    languageFilterEnabled: true,
    setUiLanguage: () => {},
    setContentLanguages: () => {},
    setLanguageFilterEnabled: () => {},
});

export const useLanguage = () => useContext(LanguageContext);

const onlySupported = (codes: string[]): string[] =>
    codes.filter((code) => availableLanguages.includes(code));

// Best-effort match of the browser's preferred languages to supported ones.
const browserLanguages = (): string[] => {
    const candidates = [
        ...(navigator.languages ?? []),
        navigator.language,
    ].filter(Boolean) as string[];

    const matched: string[] = [];
    for (const candidate of candidates) {
        const base = candidate.toLowerCase().split('-')[0];
        if (availableLanguages.includes(base) && !matched.includes(base)) {
            matched.push(base);
        }
    }
    return matched;
};

const readLocalStorage = <T,>(key: string, fallback: T): T => {
    try {
        const raw = localStorage.getItem(key);
        return raw === null ? fallback : (JSON.parse(raw) as T);
    } catch {
        return fallback;
    }
};

interface ServerPreference {
    preferred_ui_language?: string;
    preferred_languages?: string[];
    language_filter_enabled?: boolean;
}

export const LanguageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    // Anonymous defaults come from the browser; anything already stored wins.
    const [uiLanguage, setUiLanguageState] = useState<string>(() =>
        readLocalStorage(UI_LANGUAGE_KEY, '')
    );
    const [contentLanguages, setContentLanguagesState] = useState<string[]>(() =>
        onlySupported(readLocalStorage(CONTENT_LANGUAGES_KEY, browserLanguages()))
    );
    const [languageFilterEnabled, setLanguageFilterEnabledState] = useState<boolean>(() =>
        readLocalStorage(LANGUAGE_FILTER_KEY, true)
    );

    // Persist to localStorage on every change
    useEffect(() => {
        localStorage.setItem(UI_LANGUAGE_KEY, JSON.stringify(uiLanguage));
    }, [uiLanguage]);

    // Drive i18next and document direction from the chosen interface language.
    useEffect(() => {
        const resolved = uiLanguage || i18n.services.languageDetector?.detect() || undefined;
        i18n.changeLanguage(resolved || undefined);
        const active = uiLanguage || (i18n.resolvedLanguage ?? '');
        document.documentElement.dir = isRtl(active) ? 'rtl' : 'ltr';
        document.documentElement.lang = active;
    }, [uiLanguage]);
    useEffect(() => {
        localStorage.setItem(CONTENT_LANGUAGES_KEY, JSON.stringify(contentLanguages));
    }, [contentLanguages]);
    useEffect(() => {
        localStorage.setItem(LANGUAGE_FILTER_KEY, JSON.stringify(languageFilterEnabled));
    }, [languageFilterEnabled]);

    // Reconcile with the account whenever a token appears (login, or reload
    // while logged in). The server is the source of truth for logged-in users.
    useEffect(() => {
        const syncFromServer = async () => {
            if (!authService.isAuthenticated()) return;
            try {
                const profile: ServerPreference = await authService.getProfile();
                const serverUi = profile.preferred_ui_language ?? '';
                const serverContent = onlySupported(profile.preferred_languages ?? []);
                const serverFilter = profile.language_filter_enabled ?? true;

                const hasServerPreference =
                    !!serverUi || serverContent.length > 0 ||
                    profile.language_filter_enabled === false;

                if (hasServerPreference) {
                    // Adopt the account preferences
                    setUiLanguageState(serverUi);
                    setContentLanguagesState(serverContent);
                    setLanguageFilterEnabledState(serverFilter);
                } else {
                    // First login: seed the empty account from what the browser knew
                    const localUi = readLocalStorage(UI_LANGUAGE_KEY, '');
                    const localContent = onlySupported(
                        readLocalStorage(CONTENT_LANGUAGES_KEY, browserLanguages())
                    );
                    const localFilter = readLocalStorage(LANGUAGE_FILTER_KEY, true);
                    authService._updateProfile({
                        [UI_LANGUAGE_KEY]: localUi,
                        [CONTENT_LANGUAGES_KEY]: localContent,
                        [LANGUAGE_FILTER_KEY]: localFilter,
                    }).catch((e) => console.error('Failed to seed language preferences:', e));
                }
            } catch (e) {
                console.error('Failed to load language preferences:', e);
            }
        };

        syncFromServer();
        window.addEventListener('storage', syncFromServer);
        return () => window.removeEventListener('storage', syncFromServer);
    }, []);

    const pushToServer = useCallback((payload: ServerPreference) => {
        if (!authService.isAuthenticated()) return;
        authService._updateProfile(payload).catch((e) =>
            console.error('Failed to save language preferences:', e)
        );
    }, []);

    const setUiLanguage = useCallback((code: string) => {
        const normalized = code && availableLanguages.includes(code) ? code : '';
        setUiLanguageState(normalized);
        pushToServer({ [UI_LANGUAGE_KEY]: normalized });
    }, [pushToServer]);

    const setContentLanguages = useCallback((codes: string[]) => {
        // Deduplicate, preserve order, drop unsupported codes
        const unique = onlySupported(codes.filter((c, i) => codes.indexOf(c) === i));
        setContentLanguagesState(unique);
        pushToServer({ [CONTENT_LANGUAGES_KEY]: unique });
    }, [pushToServer]);

    const setLanguageFilterEnabled = useCallback((enabled: boolean) => {
        setLanguageFilterEnabledState(enabled);
        pushToServer({ [LANGUAGE_FILTER_KEY]: enabled });
    }, [pushToServer]);

    const value = useMemo(
        () => ({
            uiLanguage,
            contentLanguages,
            languageFilterEnabled,
            setUiLanguage,
            setContentLanguages,
            setLanguageFilterEnabled,
        }),
        [
            uiLanguage,
            contentLanguages,
            languageFilterEnabled,
            setUiLanguage,
            setContentLanguages,
            setLanguageFilterEnabled,
        ]
    );

    return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
};
