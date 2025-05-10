import { createTheme } from "@mui/material";

// Define the light theme
export const getLightTheme = () =>
    createTheme({
        palette: {
            mode: "light",
            primary: {
                main: "#6a1b9a", // deep purple
                light: "#9c4dcc",
                dark: "#38006b",
                contrastText: "#ffffff",
            },
            secondary: {
                main: "#9575cd", // lighter purple
                light: "#c7a4ff",
                dark: "#65499c",
                contrastText: "#000000",
            },
            background: {
                default: "#f8f5fd", // very light purple tint
                paper: "#ffffff",
            },
            text: {
                primary: "#212121",
                secondary: "#616161",
            },
        },
        typography: {
            fontFamily: '"Noto Sans", "Noto Sans JP", "Roboto", "Helvetica", "Arial", sans-serif',
            h1: {
                fontWeight: 500,
                color: "#6a1b9a",
            },
            h2: {
                fontWeight: 500,
                color: "#6a1b9a",
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
                        boxShadow: "0 2px 4px rgba(106, 27, 154, 0.2)",
                    },
                },
            },
            MuiCard: {
                styleOverrides: {
                    root: {
                        borderRadius: 12,
                        boxShadow: "0 4px 8px rgba(0, 0, 0, 0.05)",
                    },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: {
                        backgroundColor: "#ffffff",
                        color: "#212121",
                        boxShadow: "0 1px 3px rgba(0, 0, 0, 0.12)",
                    },
                },
            },
        },
    });
