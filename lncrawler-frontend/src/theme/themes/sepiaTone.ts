import { ThemeOption } from "../types";
import { makeTheme, ThemeTokens } from "../makeTheme";

const sepiaTokens: ThemeTokens = {
    palette: {
        mode: "light",
        primary: {
            main: "#8b5a2b",
            light: "#a67c52",
            dark: "#6d4520",
            contrastText: "#f8f0e3",
        },
        secondary: {
            main: "#d2b48c",
            light: "#e8d6b3",
            dark: "#b89a6f",
            contrastText: "#4b3621",
        },
        background: {
            default: "#f5e8d3",
            paper: "#f8f0e3",
        },
        text: {
            primary: "#4b3621",
            secondary: "#705c46",
        },
        error: {
            main: "#b33c3c",
            light: "#c46666",
            dark: "#8f2e2e",
        },
        success: {
            main: "#5c8c3e",
            light: "#7ea65b",
            dark: "#467032",
        },
        info: {
            main: "#5a7a99",
            light: "#7c95ac",
            dark: "#445f75",
        },
        warning: {
            main: "#d18f2d",
            light: "#dba95a",
            dark: "#a5711f",
        },
    },
    typography: {
        fontFamily: '"Merriweather", "Noto Serif JP", serif',
        fontSize: 14,
        h1: {
            fontFamily: '"Merriweather", serif',
            fontWeight: 700,
            color: "#8b5a2b",
            letterSpacing: "-0.02em",
            fontSize: "2.2rem",
        },
        h2: {
            fontFamily: '"Merriweather", serif',
            fontWeight: 700,
            color: "#8b5a2b",
            letterSpacing: "-0.02em",
            fontSize: "1.9rem",
        },
        h3: {
            fontFamily: '"Merriweather", serif',
            fontWeight: 600,
            letterSpacing: "-0.01em",
            fontSize: "1.6rem",
        },
        h4: {
            fontFamily: '"Merriweather", serif',
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
        body1: {
            lineHeight: 1.7,
            fontSize: "0.95rem",
        },
        body2: {
            lineHeight: 1.6,
            fontSize: "0.875rem",
        },
    },
    radius: 6,
    button: {
        radius: 4,
        brandGradient: "linear-gradient(135deg, #8b5a2b 0%, #a67c52 100%)",
        brandGradientHover: "linear-gradient(135deg, #8b5a2b 10%, #9a6e44 100%)",
        primaryShadow: "0 2px 8px rgba(139, 90, 43, 0.3)",
        primaryHoverShadow: "0 4px 12px rgba(139, 90, 43, 0.4)",
    },
    card: {
        radius: 8,
        shadow: "0 2px 8px rgba(75, 54, 33, 0.08)",
        hoverShadow: "0 6px 16px rgba(139, 90, 43, 0.15)",
        background: "#f8f0e3",
        border: "1px solid rgba(139, 90, 43, 0.1)",
    },
    appBar: {
        background: "rgba(248, 240, 227, 0.95)",
        color: "#4b3621",
        shadow: "0 2px 8px rgba(75, 54, 33, 0.1)",
    },
    dividerColor: "rgba(139, 90, 43, 0.15)",
    paperShadows: [
        "0 1px 6px rgba(75, 54, 33, 0.06)",
        "0 2px 10px rgba(75, 54, 33, 0.1)",
        "0 3px 12px rgba(75, 54, 33, 0.12)",
    ],
    chipPrimaryColor: "#f5e8d3",
    scrollbar: {
        color: "#d2b48c #f5e8d3",
        track: "#f5e8d3",
        thumb: "#d2b48c",
        thumbHover: "#8b5a2b",
    },
};

export const getSepiaToneTheme = () => makeTheme(sepiaTokens);

export const sepiaToneTheme: ThemeOption = {
    id: "sepia",
    name: "Sepia",
    isDark: false,
    getTheme: getSepiaToneTheme,
    hidden: false,
    password: undefined,
    font: {
        family: '"Merriweather", "Noto Serif JP", serif',
        url: "https://fonts.googleapis.com/css2?family=Merriweather:wght@300;400;700&family=Noto+Serif+JP:wght@400;700&display=swap",
    },
};
