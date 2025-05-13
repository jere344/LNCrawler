import { createTheme } from "@mui/material";

// Define the dark theme
export const getDarkTheme = () =>
    createTheme({
        palette: {
            mode: "dark",
            primary: {
                main: "#c8a4ff", // luminous purple
                light: "#f4deff",
                dark: "#9c78cc",
                contrastText: "#11071e",
            },
            secondary: {
                main: "#ad8ee6", // soft lavender
                light: "#dfbeff",
                dark: "#7c61b3",
                contrastText: "#11071e",
            },
            background: {
                default: "#13101a", // deep violet-tinted black
                paper: "#1c1726", // rich dark purple-black
            },
            text: {
                primary: "#e9e0f5", // soft white with purple tint
                secondary: "#c3b8d9", // muted lavender
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
            fontFamily: '"Nunito", "Noto Sans", "Roboto", "Helvetica", "Arial", sans-serif',
            h1: {
                fontFamily: '"Libre Baskerville", "Georgia", serif',
                fontWeight: 700,
                color: "#c8a4ff",
                letterSpacing: "-0.01em",
            },
            h2: {
                fontFamily: '"Libre Baskerville", "Georgia", serif',
                fontWeight: 700,
                color: "#c8a4ff",
                letterSpacing: "-0.01em",
            },
            h3: {
                fontFamily: '"Libre Baskerville", "Georgia", serif',
                fontWeight: 600,
                letterSpacing: "-0.01em",
            },
            h4: {
                fontFamily: '"Libre Baskerville", "Georgia", serif',
                fontWeight: 600,
                letterSpacing: "-0.01em",
            },
            h5: {
                fontWeight: 600,
            },
            h6: {
                fontWeight: 600,
            },
            subtitle1: {
                fontWeight: 500,
                fontSize: "1.1rem",
            },
            subtitle2: {
                fontWeight: 500,
                fontSize: "0.95rem",
            },
            body1: {
                lineHeight: 1.7,
                fontSize: "1.05rem",
            },
            body2: {
                lineHeight: 1.6,
            },
        },
        shape: {
            borderRadius: 10,
        },
        components: {
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 8,
                        textTransform: "none",
                        padding: "8px 20px",
                        fontSize: "0.95rem",
                        fontWeight: 600,
                    },
                    containedPrimary: {
                        boxShadow: "0 4px 12px rgba(200, 164, 255, 0.3)",
                        background: "linear-gradient(135deg, #9c78cc 0%, #c8a4ff 100%)",
                        "&:hover": {
                            boxShadow: "0 6px 16px rgba(200, 164, 255, 0.4)",
                            background: "linear-gradient(135deg, #9c78cc 10%, #b290e3 100%)",
                        },
                    },
                    outlinedPrimary: {
                        borderWidth: 2,
                    },
                },
            },
            MuiCard: {
                styleOverrides: {
                    root: {
                        borderRadius: 12,
                        boxShadow: "0 6px 16px rgba(0, 0, 0, 0.3)",
                        backgroundColor: "#1c1726",
                        backgroundImage: "linear-gradient(135deg, #1c1726 0%, #22182e 100%)",
                        transition: "transform 0.3s ease, box-shadow 0.3s ease",
                        borderLeft: "1px solid rgba(200, 164, 255, 0.1)",
                        borderTop: "1px solid rgba(200, 164, 255, 0.1)",
                        "&:hover": {
                            boxShadow: "0 8px 24px rgba(200, 164, 255, 0.2)",
                            transform: "translateY(-2px)",
                        },
                    },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: {
                        backgroundColor: "rgba(28, 23, 38, 0.95)",
                        backdropFilter: "blur(10px)",
                        boxShadow: "0 2px 10px rgba(0, 0, 0, 0.2)",
                    },
                },
            },
            MuiDivider: {
                styleOverrides: {
                    root: {
                        borderColor: "rgba(200, 164, 255, 0.15)",
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                    },
                    elevation1: {
                        boxShadow: "0 2px 10px rgba(0, 0, 0, 0.2)",
                    },
                    elevation2: {
                        boxShadow: "0 4px 16px rgba(0, 0, 0, 0.25)",
                    },
                    elevation3: {
                        boxShadow: "0 6px 18px rgba(0, 0, 0, 0.3)",
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 16,
                        fontWeight: 500,
                    },
                    colorPrimary: {
                        background: "linear-gradient(135deg, #9c78cc 0%, #c8a4ff 100%)",
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
                        scrollbarWidth: "thin",
                        scrollbarColor: "#9c78cc #13101a",
                        "&::-webkit-scrollbar": {
                            width: "8px",
                            height: "8px",
                        },
                        "&::-webkit-scrollbar-track": {
                            background: "#13101a",
                        },
                        "&::-webkit-scrollbar-thumb": {
                            background: "#9c78cc",
                            borderRadius: "4px",
                        },
                        "&::-webkit-scrollbar-thumb:hover": {
                            background: "#c8a4ff",
                        },
                    },
                },
            },
        },
    });
