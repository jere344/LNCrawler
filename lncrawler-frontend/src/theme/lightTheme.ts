import { createTheme } from "@mui/material";

export const getLightTheme = () =>
    createTheme({
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
                        padding: "6px 16px",
                        fontSize: "0.875rem",
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
                        borderRadius: 10,
                        boxShadow: "0 3px 12px rgba(0, 0, 0, 0.04)",
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
                        boxShadow: "0 1px 8px rgba(0, 0, 0, 0.03)",
                    },
                    elevation2: {
                        boxShadow: "0 2px 12px rgba(0, 0, 0, 0.05)",
                    },
                    elevation3: {
                        boxShadow: "0 3px 14px rgba(0, 0, 0, 0.06)",
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 12,
                        fontWeight: 500,
                        height: "28px",
                        "& .MuiChip-label": {
                            padding: "0 10px",
                        },
                    },
                    colorPrimary: {
                        background: "linear-gradient(135deg, #5d3a8e 0%, #7952b3 100%)",
                    },
                },
            },
            MuiTypography: {
                styleOverrides: {
                    gutterBottom: {
                        marginBottom: "0.6em",
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
                    "& .MuiContainer-root": {
                        paddingLeft: "12px",
                        paddingRight: "12px",
                    },
                    "& .MuiCardContent-root": {
                        padding: "16px",
                        "&:last-child": {
                            paddingBottom: "16px",
                        },
                    },
                    "& .MuiCardActions-root": {
                        padding: "8px 12px",
                    },
                    "& .MuiDialogContent-root": {
                        padding: "16px",
                    },
                    "& .MuiDialogActions-root": {
                        padding: "8px 12px",
                    },
                    "& .MuiListItem-root": {
                        paddingTop: "6px",
                        paddingBottom: "6px",
                    },
                },
            },
        },
    });
