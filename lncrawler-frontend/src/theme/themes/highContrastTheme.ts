import { createTheme } from "@mui/material";
import { ThemeOption } from "../types";

export const getHighContrastTheme = () =>
    createTheme({
        palette: {
            mode: "dark",
            primary: {
                main: "#ffff00", // Bright yellow
                light: "#ffff66",
                dark: "#cccc00",
                contrastText: "#000000",
            },
            secondary: {
                main: "#00ffff", // Cyan
                light: "#66ffff",
                dark: "#00cccc",
                contrastText: "#000000",
            },
            background: {
                default: "#000000", // Pure black background
                paper: "#121212",
            },
            text: {
                primary: "#ffffff", // Pure white text
                secondary: "#eeeeee",
            },
            error: {
                main: "#ff0000", // Bright red
                light: "#ff3333",
                dark: "#cc0000",
                contrastText: "#ffffff",
            },
            success: {
                main: "#00ff00", // Bright green
                light: "#66ff66",
                dark: "#00cc00",
                contrastText: "#000000",
            },
            info: {
                main: "#00ffff", // Bright cyan
                light: "#66ffff",
                dark: "#00cccc",
                contrastText: "#000000",
            },
            warning: {
                main: "#ffaa00", // Bright orange
                light: "#ffcc66",
                dark: "#cc8800",
                contrastText: "#000000",
            },
        },
        typography: {
            fontFamily: '"Inter", "Noto Sans JP", sans-serif',
            fontSize: 16, // Slightly larger base font size
            h1: {
                fontFamily: '"Source Serif Pro", serif',
                fontWeight: 700,
                color: "#ffff00", // Yellow headers
                letterSpacing: "-0.02em",
                fontSize: "2.4rem",
            },
            h2: {
                fontFamily: '"Source Serif Pro", serif',
                fontWeight: 700,
                color: "#ffff00",
                letterSpacing: "-0.02em",
                fontSize: "2.1rem",
            },
            h3: {
                fontFamily: '"Source Serif Pro", serif',
                fontWeight: 700,
                letterSpacing: "-0.01em",
                fontSize: "1.8rem",
                color: "#ffff00",
            },
            h4: {
                fontFamily: '"Source Serif Pro", serif',
                fontWeight: 700,
                letterSpacing: "-0.01em",
                fontSize: "1.6rem",
                color: "#ffff00",
            },
            h5: {
                fontWeight: 700,
                fontSize: "1.4rem",
                color: "#ffff00",
            },
            h6: {
                fontWeight: 700,
                fontSize: "1.2rem",
                color: "#ffff00",
            },
            subtitle1: {
                fontWeight: 600,
                fontSize: "1.1rem",
            },
            subtitle2: {
                fontWeight: 600,
                fontSize: "1rem",
            },
            body1: {
                lineHeight: 1.7,
                fontSize: "1rem",
            },
            body2: {
                lineHeight: 1.6,
                fontSize: "0.95rem",
            },
        },
        spacing: 8,
        shape: {
            borderRadius: 8,
        },
        components: {
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 6,
                        textTransform: "none",
                        padding: "8px 20px",
                        fontSize: "1rem",
                        fontWeight: 700,
                    },
                    containedPrimary: {
                        boxShadow: "0 4px 12px rgba(255, 255, 0, 0.5)",
                        backgroundColor: "#ffff00",
                        color: "#000000",
                        "&:hover": {
                            boxShadow: "0 6px 16px rgba(255, 255, 0, 0.6)",
                            backgroundColor: "#cccc00",
                        },
                    },
                    outlinedPrimary: {
                        borderWidth: 3,
                        borderColor: "#ffff00",
                        color: "#ffff00",
                    },
                },
            },
            MuiCard: {
                styleOverrides: {
                    root: {
                        borderRadius: 10,
                        boxShadow: "0 4px 12px rgba(255, 255, 255, 0.2)",
                        backgroundColor: "#121212",
                        border: "2px solid #ffffff",
                        transition: "transform 0.3s ease, box-shadow 0.3s ease",
                        "&:hover": {
                            boxShadow: "0 8px 24px rgba(255, 255, 255, 0.3)",
                            transform: "translateY(-2px)",
                        },
                    },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: {
                        backgroundColor: "#000000",
                        boxShadow: "0 2px 10px rgba(255, 255, 255, 0.3)",
                    },
                },
            },
            MuiDivider: {
                styleOverrides: {
                    root: {
                        borderColor: "#ffffff",
                        borderWidth: "2px",
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                    },
                    elevation1: {
                        boxShadow: "0 1px 8px rgba(255, 255, 255, 0.2)",
                    },
                    elevation2: {
                        boxShadow: "0 2px 12px rgba(255, 255, 255, 0.25)",
                    },
                    elevation3: {
                        boxShadow: "0 4px 14px rgba(255, 255, 255, 0.3)",
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 12,
                        fontWeight: 700,
                        height: "32px",
                        "& .MuiChip-label": {
                            padding: "0 12px",
                        },
                    },
                    colorPrimary: {
                        backgroundColor: "#ffff00",
                        color: "#000000",
                    },
                },
            },
            MuiTypography: {
                styleOverrides: {
                    gutterBottom: {
                        marginBottom: "0.8em",
                    },
                },
            },
            MuiCssBaseline: {
                styleOverrides: {
                    body: {
                        scrollbarWidth: "thick",
                        scrollbarColor: "#ffff00 #000000",
                        "&::-webkit-scrollbar": {
                            width: "12px",
                            height: "12px",
                        },
                        "&::-webkit-scrollbar-track": {
                            background: "#000000",
                            border: "1px solid #ffffff",
                        },
                        "&::-webkit-scrollbar-thumb": {
                            background: "#ffff00",
                            borderRadius: "6px",
                            border: "2px solid #000000",
                        },
                        "&::-webkit-scrollbar-thumb:hover": {
                            background: "#cccc00",
                        },
                    },
                    "& .MuiContainer-root": {
                        paddingLeft: "16px",
                        paddingRight: "16px",
                    },
                    "& .MuiCardContent-root": {
                        padding: "20px",
                        "&:last-child": {
                            paddingBottom: "20px",
                        },
                    },
                    "& .MuiCardActions-root": {
                        padding: "12px 16px",
                    },
                    "& .MuiDialogContent-root": {
                        padding: "20px",
                    },
                    "& .MuiDialogActions-root": {
                        padding: "12px 16px",
                    },
                    "& .MuiListItem-root": {
                        paddingTop: "8px",
                        paddingBottom: "8px",
                    },
                    "& a": {
                        color: "#00ffff", // Bright cyan for links
                        textDecoration: "underline",
                        fontWeight: 700,
                    },
                    "& *:focus": {
                        outline: "3px solid #ffff00 !important",
                        outlineOffset: "2px",
                    },
                },
            },
        },
    });

export const highContrastTheme: ThemeOption = {
    id: "highContrast",
    name: "High Contrast",
    isDark: true,
    getTheme: getHighContrastTheme,
    hidden: false,
    password: undefined,
    font: {
        family: '"Inter", "Noto Sans JP", sans-serif',
        url: "https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Source+Serif+Pro:wght@600;700&display=swap",
    },
};
