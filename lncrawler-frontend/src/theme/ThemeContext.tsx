import React, { createContext, useState, useContext, useMemo, useCallback, useEffect } from "react";
import { Theme } from "@mui/material";
import { ThemeId, ThemeOption } from "./types";
import { availableThemes, getThemeById } from "./availableThemes";

type ThemeContextType = {
    currentThemeId: ThemeId;
    setThemeById: (id: ThemeId) => void;
    isDarkMode: boolean;
    theme: Theme;
    availableThemes: ThemeOption[];
};

const ThemeContext = createContext<ThemeContextType>({
    currentThemeId: "light",
    setThemeById: () => {},
    isDarkMode: false,
    theme: getThemeById("light").getTheme(),
    availableThemes: [],
});

// Helper function to load Google Fonts
const loadGoogleFont = (url: string | undefined) => {
    if (!url) return;

    // Check if this font is already loaded
    const existingLink = document.head.querySelector(`link[href="${url}"]`);
    if (existingLink) return;

    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = url;
    document.head.appendChild(link);
};

export const useTheme = () => useContext(ThemeContext);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    // Get initial theme preference from localStorage or system preference
    const getInitialThemeId = (): ThemeId => {
        const savedThemeId = localStorage.getItem("themeId");

        if (savedThemeId && availableThemes.some((theme) => theme.id === savedThemeId)) {
            return savedThemeId;
        }

        // If no saved theme or invalid theme, check system preference for dark/light
        const prefersDarkMode = window.matchMedia("(prefers-color-scheme: dark)").matches;
        return prefersDarkMode ? "dark" : "light";
    };

    const [currentThemeId, setCurrentThemeId] = useState<ThemeId>(getInitialThemeId);

    const setThemeById = useCallback((id: ThemeId) => {
        setCurrentThemeId(id);
    }, []);

    useEffect(() => {
        localStorage.setItem("themeId", currentThemeId);
    }, [currentThemeId]);

    const currentTheme = useMemo(() => {
        return getThemeById(currentThemeId);
    }, [currentThemeId]);

    // Load font when theme changes
    useEffect(() => {
        if (currentTheme.font?.url) {
            loadGoogleFont(currentTheme.font.url);
        }
    }, [currentTheme]);

    const theme = useMemo(() => {
        return currentTheme.getTheme();
    }, [currentTheme]);

    const isDarkMode = useMemo(() => {
        return currentTheme.isDark;
    }, [currentTheme]);

    const value = useMemo(
        () => ({
            currentThemeId,
            setThemeById,
            isDarkMode,
            theme,
            availableThemes,
        }),
        [currentThemeId, setThemeById, isDarkMode, theme]
    );

    return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};
