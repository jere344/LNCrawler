import { ThemeOption } from "../types";
import { makeTheme, ThemeTokens } from "../makeTheme";

const lightTokens: ThemeTokens = {
    palette: {
        mode: "light",
        primary: {
            main: "#5d3a8e",
            light: "#8c68be",
            dark: "#3d1e6b",
            contrastText: "#ffffff",
        },
        secondary: {
            main: "#c9a0dc",
            light: "#ffd1ff",
            dark: "#9772aa",
            contrastText: "#333333",
        },
        background: {
            default: "#f8f6ff",
            paper: "#ffffff",
        },
        text: {
            primary: "#2d2a35",
            secondary: "#5f5670",
        },
        error: {
            main: "#d32f2f",
            light: "#ef5350",
            dark: "#c62828",
        },
        success: {
            main: "#388e3c",
            light: "#4caf50",
            dark: "#2e7d32",
        },
        info: {
            main: "#3b6ea8",
            light: "#64b5f6",
            dark: "#0d47a1",
        },
        warning: {
            main: "#f57c00",
            light: "#ffb74d",
            dark: "#e65100",
        },
    },
    typography: {
        fontFamily: '"Inter", "Noto Sans JP", sans-serif',
        fontSize: 14,
        h1: {
            fontFamily: '"Source Serif Pro", serif',
            fontWeight: 700,
            color: "#5d3a8e",
            letterSpacing: "-0.02em",
            fontSize: "2.2rem",
        },
        h2: {
            fontFamily: '"Source Serif Pro", serif',
            fontWeight: 700,
            color: "#5d3a8e",
            letterSpacing: "-0.02em",
            fontSize: "1.9rem",
        },
        h3: {
            fontFamily: '"Source Serif Pro", serif',
            fontWeight: 600,
            letterSpacing: "-0.01em",
            fontSize: "1.6rem",
        },
        h4: {
            fontFamily: '"Source Serif Pro", serif',
            fontWeight: 600,
            letterSpacing: "-0.01em",
            fontSize: "1.4rem",
        },
        h5: {
            fontWeight: 600,
            fontSize: "1.2rem",
        },
        h6: {
            fontWeight: 600,
            fontSize: "1.05rem",
        },
        subtitle1: {
            fontWeight: 500,
            fontSize: "1rem",
        },
        subtitle2: {
            fontWeight: 500,
            fontSize: "0.9rem",
        },
        body1: {
            lineHeight: 1.6,
            fontSize: "0.95rem",
        },
        body2: {
            lineHeight: 1.5,
            fontSize: "0.875rem",
        },
    },
    radius: 8,
    button: {
        radius: 6,
        brandGradient: "linear-gradient(135deg, #5d3a8e 0%, #7952b3 100%)",
        brandGradientHover: "linear-gradient(135deg, #5d3a8e 10%, #6e47a6 100%)",
        primaryShadow: "0 4px 12px rgba(93, 58, 142, 0.25)",
        primaryHoverShadow: "0 6px 16px rgba(93, 58, 142, 0.35)",
    },
    card: {
        radius: 10,
        shadow: "0 3px 12px rgba(0, 0, 0, 0.04)",
        hoverShadow: "0 8px 24px rgba(93, 58, 142, 0.12)",
    },
    appBar: {
        background: "rgba(255, 255, 255, 0.95)",
        color: "#2d2a35",
        shadow: "0 2px 10px rgba(0, 0, 0, 0.06)",
    },
    dividerColor: "rgba(93, 58, 142, 0.12)",
    paperShadows: [
        "0 1px 8px rgba(0, 0, 0, 0.03)",
        "0 2px 12px rgba(0, 0, 0, 0.05)",
        "0 3px 14px rgba(0, 0, 0, 0.06)",
    ],
    chipPrimaryColor: "#ffffff",
    scrollbar: {
        color: "#c9a0dc #f8f6ff",
        track: "#f8f6ff",
        thumb: "#c9a0dc",
        thumbHover: "#5d3a8e",
    },
    gutterBottomMargin: "0.6em",
};

export const getLightTheme = () => makeTheme(lightTokens);

export const lightTheme: ThemeOption = {
    id: "light",
    isDark: false,
    getTheme: getLightTheme,
    hidden: false,
    password: undefined,
    font: {
        family: '"Roboto", "Helvetica", "Arial", sans-serif',
        url: "https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap"
    }
};
