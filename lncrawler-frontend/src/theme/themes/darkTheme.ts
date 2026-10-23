import { ThemeOption } from "../types";
import { makeTheme, ThemeTokens } from "../makeTheme";

const darkTokens: ThemeTokens = {
    palette: {
        mode: "dark",
        primary: {
            main: "#c8a4ff",
            light: "#f4deff",
            dark: "#9c78cc",
            contrastText: "#11071e",
        },
        secondary: {
            main: "#ad8ee6",
            light: "#dfbeff",
            dark: "#7c61b3",
            contrastText: "#11071e",
        },
        background: {
            default: "#13101a",
            paper: "#1c1726",
        },
        text: {
            primary: "#e9e0f5",
            secondary: "#c3b8d9",
        },
        error: {
            main: "#f44336",
            light: "#e57373",
            dark: "#d32f2f",
        },
        success: {
            main: "#66bb6a",
            light: "#81c784",
            dark: "#388e3c",
        },
        info: {
            main: "#64b5f6",
            light: "#90caf9",
            dark: "#3b6ea8",
        },
        warning: {
            main: "#ffb74d",
            light: "#ffd54f",
            dark: "#f57c00",
        },
    },
    typography: {
        fontFamily: '"Inter", "Noto Sans JP", sans-serif',
        fontSize: 14,
        h1: {
            fontFamily: '"Source Serif Pro", serif',
            fontWeight: 700,
            color: "#c8a4ff",
            letterSpacing: "-0.02em",
            fontSize: "2.2rem",
        },
        h2: {
            fontFamily: '"Source Serif Pro", serif',
            fontWeight: 700,
            color: "#c8a4ff",
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
        brandGradient: "linear-gradient(135deg, #9c78cc 0%, #c8a4ff 100%)",
        brandGradientHover: "linear-gradient(135deg, #9c78cc 10%, #b290e3 100%)",
        primaryShadow: "0 4px 12px rgba(200, 164, 255, 0.3)",
        primaryHoverShadow: "0 6px 16px rgba(200, 164, 255, 0.4)",
        primaryDisabledColor: "rgba(17, 7, 30, 0.5)",
    },
    card: {
        radius: 10,
        shadow: "0 4px 12px rgba(0, 0, 0, 0.3)",
        hoverShadow: "0 8px 24px rgba(200, 164, 255, 0.2)",
        background: "#1c1726",
        backgroundImage: "linear-gradient(135deg, #1c1726 0%, #22182e 100%)",
        borderTopLeft: "1px solid rgba(200, 164, 255, 0.1)",
    },
    appBar: {
        background: "rgba(28, 23, 38, 0.95)",
        shadow: "0 2px 10px rgba(0, 0, 0, 0.2)",
    },
    dividerColor: "rgba(200, 164, 255, 0.15)",
    paperShadows: [
        "0 1px 8px rgba(0, 0, 0, 0.2)",
        "0 2px 12px rgba(0, 0, 0, 0.25)",
        "0 4px 14px rgba(0, 0, 0, 0.3)",
    ],
    chipPrimaryColor: "#11071e",
    scrollbar: {
        color: "#9c78cc #13101a",
        track: "#13101a",
        thumb: "#9c78cc",
        thumbHover: "#c8a4ff",
    },
    gutterBottomMargin: "0.6em",
};

export const getDarkTheme = () => makeTheme(darkTokens);

export const darkTheme: ThemeOption = {
    id: "dark",
    isDark: true,
    getTheme: getDarkTheme,
    hidden: false,
    password: undefined,
    font: {
        family: '"Inter", "Noto Sans JP", sans-serif',
        url: "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Serif+Pro:wght@600;700&family=Noto+Sans+JP:wght@400;500;700&display=swap",
    },
};
