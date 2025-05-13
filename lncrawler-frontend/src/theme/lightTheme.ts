import { createTheme } from "@mui/material";

// Define the light theme
export const getLightTheme = () =>
    createTheme({
        palette: {
            mode: "light",
            primary: {
                main: "#5d3a8e", // rich royal purple
                light: "#8c68be",
                dark: "#3d1e6b",
                contrastText: "#ffffff",
            },
            secondary: {
                main: "#c9a0dc", // elegant lavender
                light: "#ffd1ff",
                dark: "#9772aa",
                contrastText: "#333333",
            },
            background: {
                default: "#f8f6ff", // soft cream-purple tint
                paper: "#ffffff",
            },
            text: {
                primary: "#2d2a35", // rich dark purple-tinted gray
                secondary: "#5f5670", // muted purple-gray
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
            fontFamily: '"Nunito", "Noto Sans", "Roboto", "Helvetica", "Arial", sans-serif',
            h1: {
                fontFamily: '"Libre Baskerville", "Georgia", serif',
                fontWeight: 700,
                color: "#5d3a8e",
                letterSpacing: "-0.01em",
            },
            h2: {
                fontFamily: '"Libre Baskerville", "Georgia", serif',
                fontWeight: 700,
                color: "#5d3a8e",
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
                        boxShadow: "0 4px 12px rgba(93, 58, 142, 0.25)",
                        background: "linear-gradient(135deg, #5d3a8e 0%, #7952b3 100%)",
                        "&:hover": {
                            boxShadow: "0 6px 16px rgba(93, 58, 142, 0.35)",
                            background: "linear-gradient(135deg, #5d3a8e 10%, #6e47a6 100%)",
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
                        boxShadow: "0 6px 16px rgba(0, 0, 0, 0.05)",
                        transition: "transform 0.3s ease, box-shadow 0.3s ease",
                        "&:hover": {
                            boxShadow: "0 8px 24px rgba(93, 58, 142, 0.12)",
                            transform: "translateY(-2px)",
                        },
                    },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: {
                        backgroundColor: "rgba(255, 255, 255, 0.95)",
                        color: "#2d2a35",
                        backdropFilter: "blur(10px)",
                        boxShadow: "0 2px 10px rgba(0, 0, 0, 0.06)",
                    },
                },
            },
            MuiDivider: {
                styleOverrides: {
                    root: {
                        borderColor: "rgba(93, 58, 142, 0.12)",
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                    },
                    elevation1: {
                        boxShadow: "0 2px 10px rgba(0, 0, 0, 0.05)",
                    },
                    elevation2: {
                        boxShadow: "0 4px 16px rgba(0, 0, 0, 0.07)",
                    },
                    elevation3: {
                        boxShadow: "0 6px 18px rgba(0, 0, 0, 0.08)",
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
                        background: "linear-gradient(135deg, #5d3a8e 0%, #7952b3 100%)",
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
                        scrollbarColor: "#c9a0dc #f8f6ff",
                        "&::-webkit-scrollbar": {
                            width: "8px",
                            height: "8px",
                        },
                        "&::-webkit-scrollbar-track": {
                            background: "#f8f6ff",
                        },
                        "&::-webkit-scrollbar-thumb": {
                            background: "#c9a0dc",
                            borderRadius: "4px",
                        },
                        "&::-webkit-scrollbar-thumb:hover": {
                            background: "#5d3a8e",
                        },
                    },
                },
            },
        },
    });
