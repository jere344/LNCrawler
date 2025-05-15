import { createTheme } from "@mui/material";

// Define the dark theme
export const getDarkTheme = () =>
    createTheme({
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
            fontSize: 14, // Reduced base font size
            h1: {
                fontFamily: '"Source Serif Pro", serif',
                fontWeight: 700,
                color: "#c8a4ff",
                letterSpacing: "-0.02em",
                fontSize: "2.2rem", // Reduced from default
            },
            h2: {
                fontFamily: '"Source Serif Pro", serif',
                fontWeight: 700,
                color: "#c8a4ff",
                letterSpacing: "-0.02em",
                fontSize: "1.9rem", // Reduced from default
            },
            h3: {
                fontFamily: '"Source Serif Pro", serif',
                fontWeight: 600,
                letterSpacing: "-0.01em",
                fontSize: "1.6rem", // Reduced from default
            },
            h4: {
                fontFamily: '"Source Serif Pro", serif',
                fontWeight: 600,
                letterSpacing: "-0.01em",
                fontSize: "1.4rem", // Reduced from default
            },
            h5: {
                fontWeight: 600,
                fontSize: "1.2rem", // Reduced from default
            },
            h6: {
                fontWeight: 600,
                fontSize: "1.05rem", // Reduced from default
            },
            subtitle1: {
                fontWeight: 500,
                fontSize: "1rem", // Reduced from 1.1rem
            },
            subtitle2: {
                fontWeight: 500,
                fontSize: "0.9rem", // Reduced from 0.95rem
            },
            body1: {
                lineHeight: 1.6, // Reduced from 1.7
                fontSize: "0.95rem", // Reduced from 1.05rem
            },
            body2: {
                lineHeight: 1.5, // Reduced from 1.6
                fontSize: "0.875rem", // Added explicit size
            },
        },
        spacing: 8, // Base spacing unit
        shape: {
            borderRadius: 8, // Reduced from 10
        },
        components: {
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 6, // Reduced from 8
                        textTransform: "none",
                        padding: "6px 16px", // Reduced from 8px 20px
                        fontSize: "0.875rem", // Reduced from 0.95rem
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
                        borderRadius: 10, // Reduced from 12
                        boxShadow: "0 4px 12px rgba(0, 0, 0, 0.3)", // Reduced shadow
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
                        boxShadow: "0 1px 8px rgba(0, 0, 0, 0.2)", // Reduced shadow
                    },
                    elevation2: {
                        boxShadow: "0 2px 12px rgba(0, 0, 0, 0.25)", // Reduced shadow
                    },
                    elevation3: {
                        boxShadow: "0 4px 14px rgba(0, 0, 0, 0.3)", // Reduced shadow
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 12, // Reduced from 16
                        fontWeight: 500,
                        height: "28px", // More compact height
                        "& .MuiChip-label": {
                            padding: "0 10px", // Reduced padding
                        },
                    },
                    colorPrimary: {
                        background: "linear-gradient(135deg, #9c78cc 0%, #c8a4ff 100%)",
                    },
                },
            },
            MuiTypography: {
                styleOverrides: {
                    gutterBottom: {
                        marginBottom: "0.6em", // Reduced from 0.8em
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
                    // Add more compact defaults
                    "& .MuiContainer-root": {
                        paddingLeft: "12px",
                        paddingRight: "12px",
                    },
                    "& .MuiCardContent-root": {
                        padding: "16px", // Reduced padding
                        "&:last-child": {
                            paddingBottom: "16px", // Consistent padding
                        },
                    },
                    "& .MuiCardActions-root": {
                        padding: "8px 12px", // Reduced padding
                    },
                    "& .MuiDialogContent-root": {
                        padding: "16px", // Reduced padding
                    },
                    "& .MuiDialogActions-root": {
                        padding: "8px 12px", // Reduced padding
                    },
                    "& .MuiListItem-root": {
                        paddingTop: "6px", // Reduced padding
                        paddingBottom: "6px", // Reduced padding
                    },
                },
            },
        },
    });
