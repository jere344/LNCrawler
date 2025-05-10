import React, { createContext, useState, useContext, useMemo, useCallback, useEffect } from "react";
import { Theme } from "@mui/material";
import { getLightTheme } from "./lightTheme";
import { getDarkTheme } from "./darkTheme";

type ThemeContextType = {
    isDarkMode: boolean;
    toggleTheme: () => void;
    theme: Theme;
};

const ThemeContext = createContext<ThemeContextType>({
    isDarkMode: false,
    toggleTheme: () => {},
    theme: getLightTheme(),
});

export const useTheme = () => useContext(ThemeContext);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    // Get initial theme preference from localStorage or system preference
    const getInitialThemePreference = (): boolean => {
        const savedTheme = localStorage.getItem("darkMode");
        if (savedTheme !== null) {
            return savedTheme === "true";
        }
        return window.matchMedia("(prefers-color-scheme: dark)").matches;
    };

    const [isDarkMode, setIsDarkMode] = useState<boolean>(getInitialThemePreference);

    const toggleTheme = useCallback(() => {
        setIsDarkMode((prevMode) => !prevMode);
    }, []);

    useEffect(() => {
        localStorage.setItem("darkMode", isDarkMode.toString());
    }, [isDarkMode]);

    const theme = useMemo(() => {
        return isDarkMode ? getDarkTheme() : getLightTheme();
    }, [isDarkMode]);

    const value = useMemo(
        () => ({
            isDarkMode,
            toggleTheme,
            theme,
        }),
        [isDarkMode, toggleTheme, theme]
    );

    return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};
