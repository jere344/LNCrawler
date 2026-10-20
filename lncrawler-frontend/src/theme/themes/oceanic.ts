import { ThemeOption } from "../types";
import { makeTheme, ThemeTokens } from "../makeTheme";

const oceanicTokens: ThemeTokens = {
    palette: {
        mode: "dark",
        primary: {
            main: "#64b5f6",
            light: "#90caf9",
            dark: "#1976d2",
            contrastText: "#0a192f",
        },
        secondary: {
            main: "#4fc3f7",
            light: "#81d4fa",
            dark: "#0288d1",
            contrastText: "#0a192f",
        },
        background: {
            default: "#0a192f",
            paper: "#172a45",
        },
        text: {
            primary: "#e6f1ff",
            secondary: "#a8b2d1",
        },
        error: {
            main: "#ff5252",
            light: "#ff7b7b",
            dark: "#c50e29",
        },
        success: {
            main: "#69f0ae",
            light: "#b9f6ca",
            dark: "#00c853",
        },
        info: {
            main: "#64b5f6",
            light: "#90caf9",
            dark: "#1976d2",
        },
        warning: {
            main: "#ffab40",
            light: "#ffd180",
            dark: "#ff9100",
        },
    },
    typography: {
        fontFamily: '"JetBrains Mono", "Roboto Mono", monospace',
        fontSize: 14,
        h1: {
            fontFamily: '"Inter", sans-serif',
            fontWeight: 700,
            color: "#64b5f6",
            letterSpacing: "-0.01em",
            fontSize: "2.2rem",
        },
        h2: {
            fontFamily: '"Inter", sans-serif',
            fontWeight: 700,
            color: "#64b5f6",
            letterSpacing: "-0.01em",
            fontSize: "1.9rem",
        },
        h3: {
            fontFamily: '"Inter", sans-serif',
            fontWeight: 600,
            letterSpacing: "-0.005em",
            fontSize: "1.6rem",
        },
        h4: {
            fontFamily: '"Inter", sans-serif',
            fontWeight: 600,
            letterSpacing: "-0.005em",
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
            lineHeight: 1.6,
            fontSize: "0.95rem",
        },
        body2: {
            lineHeight: 1.5,
            fontSize: "0.875rem",
        },
    },
    radius: 4,
    button: {
        radius: 4,
        brandGradient: "linear-gradient(135deg, #1976d2 0%, #64b5f6 100%)",
        brandGradientHover: "linear-gradient(135deg, #1565c0 10%, #42a5f5 100%)",
        primaryShadow: "0 4px 12px rgba(25, 118, 210, 0.3)",
        primaryHoverShadow: "0 6px 16px rgba(25, 118, 210, 0.4)",
    },
    card: {
        radius: 6,
        shadow: "0 4px 12px rgba(0, 0, 0, 0.3)",
        hoverShadow: "0 8px 24px rgba(100, 181, 246, 0.2)",
        background: "#172a45",
        backgroundImage: "linear-gradient(135deg, #172a45 0%, #1d3050 100%)",
        borderTopLeft: "1px solid rgba(100, 181, 246, 0.1)",
    },
    appBar: {
        background: "rgba(23, 42, 69, 0.95)",
        shadow: "0 2px 10px rgba(0, 0, 0, 0.2)",
    },
    dividerColor: "rgba(100, 181, 246, 0.15)",
    paperShadows: [
        "0 1px 8px rgba(0, 0, 0, 0.2)",
        "0 2px 12px rgba(0, 0, 0, 0.25)",
        "0 4px 14px rgba(0, 0, 0, 0.3)",
    ],
    chipPrimaryColor: "#0a192f",
    scrollbar: {
        color: "#64b5f6 #0a192f",
        track: "#0a192f",
        thumb: "#1976d2",
        thumbHover: "#64b5f6",
    },
};

export const getOceanicTheme = () => makeTheme(oceanicTokens);

export const oceanicTheme: ThemeOption = {
    id: "oceanic",
    name: "Oceanic",
    isDark: true,
    getTheme: getOceanicTheme,
    hidden: false,
    password: undefined,
    font: {
        family: '"JetBrains Mono", "Roboto Mono", monospace',
        url: "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;700&family=Inter:wght@400;600;700&display=swap",
    },
};
