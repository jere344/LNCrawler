import { createTheme } from "@mui/material";

// Define the dark theme
export const getDarkTheme = () =>
    createTheme({
        palette: {
            mode: "dark",
            primary: {
                main: "#bb86fc", // lighter purple for dark mode
                light: "#eeb8ff",
                dark: "#8858c8",
                contrastText: "#000000",
            },
            secondary: {
                main: "#b39ddb", // soft purple
                light: "#e6ceff",
                dark: "#836fa9",
                contrastText: "#000000",
            },
            background: {
                default: "#121212", // standard dark background
                paper: "#1e1e1e", // slightly lighter dark
            },
            text: {
                primary: "#ffffff",
                secondary: "#b0b0b0",
            },
        },
        typography: {
            fontFamily: '"Noto Sans", "Noto Sans JP", "Roboto", "Helvetica", "Arial", sans-serif',
            h1: {
                fontWeight: 500,
                color: "#bb86fc",
            },
            h2: {
                fontWeight: 500,
                color: "#bb86fc",
            },
            h3: {
                fontWeight: 500,
            },
            h4: {
                fontWeight: 500,
            },
            h5: {
                fontWeight: 500,
            },
            h6: {
                fontWeight: 500,
            },
            subtitle1: {
                fontWeight: 400,
            },
            subtitle2: {
                fontWeight: 400,
            },
        },
        components: {
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 8,
                        textTransform: "none",
                    },
                    containedPrimary: {
                        boxShadow: "0 2px 4px rgba(187, 134, 252, 0.3)",
                    },
                },
            },
            MuiCard: {
                styleOverrides: {
                    root: {
                        borderRadius: 12,
                        boxShadow: "0 4px 8px rgba(0, 0, 0, 0.15)",
                        backgroundColor: "#1e1e1e",
                    },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: {
                        backgroundColor: "#1e1e1e",
                        boxShadow: "0 1px 3px rgba(0, 0, 0, 0.3)",
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                    },
                },
            },
        },
    });
