import { createTheme } from "@mui/material";
import { ThemeOption } from "../types";

export const getHackerTheme = () =>
    createTheme({
        palette: {
            mode: "dark",
            primary: {
                main: "#00ff00", // Bright neon green
                light: "#66ff66",
                dark: "#00cc00",
                contrastText: "#000000",
            },
            secondary: {
                main: "#32cd32", // Lime green
                light: "#5efc82",
                dark: "#008000",
                contrastText: "#000000",
            },
            background: {
                default: "#0c0c0c", // Near black
                paper: "#121212",
            },
            text: {
                primary: "#00ff00", // Neon green text
                secondary: "#88ff88",
            },
            error: {
                main: "#ff3333",
                light: "#ff6666",
                dark: "#cc0000",
            },
            success: {
                main: "#00ff00",
                light: "#66ff66",
                dark: "#00cc00",
            },
            info: {
                main: "#00ffff", // Cyan
                light: "#66ffff",
                dark: "#00cccc",
            },
            warning: {
                main: "#ffff00", // Yellow
                light: "#ffff66",
                dark: "#cccc00",
            },
        },
        typography: {
            fontFamily: '"Fira Code", "Hack", "Courier New", monospace',
            fontSize: 14,
            h1: {
                fontFamily: '"Share Tech Mono", monospace',
                fontWeight: 700,
                color: "#00ff00",
                fontSize: "2.2rem",
                textShadow: "0 0 5px #00ff00, 0 0 10px #00ff00",
            },
            h2: {
                fontFamily: '"Share Tech Mono", monospace',
                fontWeight: 700,
                color: "#00ff00",
                fontSize: "1.9rem",
                textShadow: "0 0 3px #00ff00",
            },
            h3: {
                fontFamily: '"Share Tech Mono", monospace',
                fontWeight: 600,
                fontSize: "1.6rem",
                color: "#00ff00",
            },
            h4: {
                fontFamily: '"Share Tech Mono", monospace',
                fontWeight: 600,
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
        shape: {
            borderRadius: 0, // Sharp edges for a more technical look
        },
        components: {
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 0,
                        textTransform: "uppercase",
                        padding: "6px 16px",
                        fontSize: "0.875rem",
                        fontWeight: 600,
                        fontFamily: '"Fira Code", monospace',
                        letterSpacing: "0.05em",
                    },
                    containedPrimary: {
                        boxShadow: "0 0 10px rgba(0, 255, 0, 0.5)",
                        background: "linear-gradient(180deg, #004d00 0%, #00cc00 100%)",
                        "&:hover": {
                            boxShadow: "0 0 15px rgba(0, 255, 0, 0.7)",
                            background: "linear-gradient(180deg, #006600 10%, #00ff00 100%)",
                        },
                    },
                    outlinedPrimary: {
                        borderWidth: 2,
                        borderColor: "#00ff00",
                        "&:hover": {
                            boxShadow: "0 0 10px rgba(0, 255, 0, 0.5)",
                        },
                    },
                },
            },
            MuiCard: {
                styleOverrides: {
                    root: {
                        borderRadius: 0,
                        boxShadow: "0 0 10px rgba(0, 255, 0, 0.3)",
                        backgroundColor: "#121212",
                        border: "1px solid #00ff00",
                        transition: "transform 0.3s ease, box-shadow 0.3s ease",
                        "&:hover": {
                            boxShadow: "0 0 15px rgba(0, 255, 0, 0.5)",
                            transform: "translateY(-2px)",
                        },
                        "&::before": {
                            content: '""',
                            position: "absolute",
                            top: 0,
                            left: 0,
                            right: 0,
                            height: "1px",
                            background: "linear-gradient(90deg, transparent, #00ff00, transparent)",
                        },
                    },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: {
                        backgroundColor: "rgba(12, 12, 12, 0.95)",
                        backdropFilter: "blur(10px)",
                        boxShadow: "0 0 10px rgba(0, 255, 0, 0.3)",
                        borderBottom: "1px solid #00ff00",
                    },
                },
            },
            MuiDivider: {
                styleOverrides: {
                    root: {
                        borderColor: "rgba(0, 255, 0, 0.3)",
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                        backgroundColor: "#121212",
                        border: "1px solid rgba(0, 255, 0, 0.1)",
                    },
                    elevation1: {
                        boxShadow: "0 0 5px rgba(0, 255, 0, 0.2)",
                    },
                    elevation2: {
                        boxShadow: "0 0 10px rgba(0, 255, 0, 0.25)",
                    },
                    elevation3: {
                        boxShadow: "0 0 15px rgba(0, 255, 0, 0.3)",
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 0,
                        fontWeight: 500,
                        height: "28px",
                        "& .MuiChip-label": {
                            padding: "0 10px",
                        },
                    },
                    colorPrimary: {
                        background: "linear-gradient(90deg, #004d00 0%, #00cc00 100%)",
                        color: "#000000",
                    },
                },
            },
            MuiCssBaseline: {
                styleOverrides: {
                    body: {
                        scrollbarWidth: "thin",
                        scrollbarColor: "#00ff00 #0c0c0c",
                        "&::-webkit-scrollbar": {
                            width: "8px",
                            height: "8px",
                        },
                        "&::-webkit-scrollbar-track": {
                            background: "#0c0c0c",
                        },
                        "&::-webkit-scrollbar-thumb": {
                            background: "#00cc00",
                            borderRadius: "0",
                        },
                        "&::-webkit-scrollbar-thumb:hover": {
                            background: "#00ff00",
                        },
                        "&::after": {
                            content: '""',
                            position: "fixed",
                            top: 0,
                            left: 0,
                            width: "100%",
                            height: "100%",
                            pointerEvents: "none",
                            background: "repeating-linear-gradient(rgba(0, 0, 0, 0), rgba(0, 0, 0, 0) 1px, rgba(0, 255, 0, 0.03) 1px, rgba(0, 255, 0, 0.03) 2px)",
                            zIndex: 9999,
                        },
                    },
                    "@keyframes scanline": {
                        "0%": { transform: "translateY(0)" },
                        "100%": { transform: "translateY(100vh)" }
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

export const hackerTheme: ThemeOption = {
    id: "hacker",
    name: "H4CK3R",
    isDark: true,
    getTheme: getHackerTheme,
    hidden: true,
    password: "l33t",
};
