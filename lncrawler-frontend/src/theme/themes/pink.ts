import { createTheme } from "@mui/material";
import { ThemeOption } from "../types";

export const getPinkTheme = () =>
    createTheme({
        palette: {
            mode: "light",
            primary: {
                main: "#ff4d8d",
                light: "#ff80ab",
                dark: "#c60055",
                contrastText: "#ffffff",
            },
            secondary: {
                main: "#b968c7",
                light: "#ea98ff",
                dark: "#883997",
                contrastText: "#ffffff",
            },
            background: {
                default: "#fff0f7",
                paper: "#ffffff",
            },
            text: {
                primary: "#4a0025",
                secondary: "#85004b",
            },
            error: {
                main: "#ff3d71",
                light: "#ff7a9e",
                dark: "#c60046",
            },
            success: {
                main: "#ff4d8d",
                light: "#ff80ab",
                dark: "#c60055",
            },
            info: {
                main: "#d176e1",
                light: "#ffa6ff",
                dark: "#9f45af",
            },
            warning: {
                main: "#ffa6c9",
                light: "#ffd7ff",
                dark: "#c94f98",
            },
        },
        typography: {
            fontFamily: '"Quicksand", "Poppins", sans-serif',
            fontSize: 14,
            h1: {
                fontFamily: '"Playfair Display", serif',
                fontWeight: 700,
                letterSpacing: "0.02em",
                fontSize: "2.5rem",
                background: "linear-gradient(45deg, #ff4d8d 30%, #d176e1 90%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
            },
            h2: {
                fontFamily: '"Playfair Display", serif',
                fontWeight: 700,
                letterSpacing: "0.01em",
                fontSize: "2rem",
                background: "linear-gradient(45deg, #ff4d8d 30%, #d176e1 90%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
            },
            h3: {
                fontFamily: '"Montserrat", sans-serif',
                fontWeight: 600,
                letterSpacing: "0.02em",
                fontSize: "1.7rem",
                color: "#c60055",
            },
            h4: {
                fontFamily: '"Montserrat", sans-serif',
                fontWeight: 600,
                letterSpacing: "0.01em",
                fontSize: "1.5rem",
                color: "#c60055",
            },
            h5: {
                fontWeight: 600,
                fontSize: "1.3rem",
                color: "#4a0025",
            },
            h6: {
                fontWeight: 600,
                fontSize: "1.1rem",
                color: "#4a0025",
            },
            body1: {
                lineHeight: 1.7,
                fontSize: "1rem",
                fontFamily: '"Quicksand", sans-serif',
                fontWeight: 500,
            },
            body2: {
                lineHeight: 1.6,
                fontSize: "0.9rem",
                fontFamily: '"Quicksand", sans-serif',
                fontWeight: 400,
            },
        },
        shape: {
            borderRadius: 12,
        },
        components: {
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 25,
                        textTransform: "none",
                        padding: "8px 22px",
                        fontSize: "0.95rem",
                        fontWeight: 600,
                        transition: "all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)",
                        "&:hover": {
                            transform: "translateY(-3px)",
                            boxShadow: "0 8px 20px rgba(255, 77, 141, 0.4)",
                        },
                    },
                    containedPrimary: {
                        background: "linear-gradient(45deg, #ff4d8d 30%, #ff80ab 90%)",
                        boxShadow: "0 4px 12px rgba(255, 77, 141, 0.3)",
                        "&:hover": {
                            background: "linear-gradient(45deg, #ff3d7d 30%, #ff70a1 90%)",
                        },
                    },
                    outlinedPrimary: {
                        borderWidth: 2,
                        "&:hover": {
                            borderWidth: 2,
                            background: "rgba(255, 128, 171, 0.1)",
                        },
                    },
                },
            },
            MuiCard: {
                styleOverrides: {
                    root: {
                        borderRadius: 16,
                        boxShadow: "0 6px 16px rgba(255, 77, 141, 0.15)",
                        overflow: "hidden",
                        position: "relative",
                        transition: "transform 0.3s ease, box-shadow 0.3s ease",
                        "&::before": {
                            content: '""',
                            position: "absolute",
                            top: 0,
                            left: 0,
                            width: "100%",
                            height: "100%",
                            background: "linear-gradient(135deg, rgba(255, 128, 171, 0.1) 0%, rgba(209, 118, 225, 0.1) 100%)",
                            opacity: 0,
                            transition: "opacity 0.3s ease",
                        },
                        "&:hover": {
                            transform: "translateY(-5px)",
                            boxShadow: "0 12px 28px rgba(255, 77, 141, 0.25)",
                            "&::before": {
                                opacity: 1,
                            },
                        },
                        border: "1px solid rgba(255, 128, 171, 0.2)",
                    },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: {
                        background: "linear-gradient(90deg, rgba(255, 77, 141, 0.95) 0%, rgba(185, 104, 199, 0.95) 100%)",
                        backdropFilter: "blur(8px)",
                        boxShadow: "0 4px 20px rgba(255, 77, 141, 0.3)",
                    },
                },
            },
            MuiDivider: {
                styleOverrides: {
                    root: {
                        borderImage: "linear-gradient(to right, rgba(255, 128, 171, 0.2), rgba(255, 77, 141, 0.8), rgba(255, 128, 171, 0.2)) 1",
                        borderWidth: "1px 0 0 0",
                        borderStyle: "solid",
                        height: "1px",
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                    },
                    elevation1: {
                        boxShadow: "0 2px 10px rgba(255, 77, 141, 0.15)",
                    },
                    elevation2: {
                        boxShadow: "0 3px 14px rgba(255, 77, 141, 0.2)",
                    },
                    elevation3: {
                        boxShadow: "0 5px 18px rgba(255, 77, 141, 0.25)",
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 16,
                        fontWeight: 600,
                        height: "30px",
                        "& .MuiChip-label": {
                            padding: "0 12px",
                        },
                        transition: "transform 0.2s ease, box-shadow 0.2s ease",
                        "&:hover": {
                            transform: "scale(1.05)",
                        },
                    },
                    colorPrimary: {
                        background: "linear-gradient(45deg, #ff4d8d 30%, #ff80ab 90%)",
                        boxShadow: "0 2px 8px rgba(255, 77, 141, 0.3)",
                    },
                },
            },
            MuiCssBaseline: {
                styleOverrides: {
                    body: {
                        scrollbarWidth: "thin",
                        scrollbarColor: "#ff80ab #fff0f7",
                        "&::-webkit-scrollbar": {
                            width: "8px",
                            height: "8px",
                        },
                        "&::-webkit-scrollbar-track": {
                            background: "#fff0f7",
                        },
                        "&::-webkit-scrollbar-thumb": {
                            background: "#ff80ab",
                            borderRadius: "10px",
                        },
                        "&::-webkit-scrollbar-thumb:hover": {
                            background: "#ff4d8d",
                        },
                        "::selection": {
                            background: "rgba(255, 77, 141, 0.3)",
                            color: "#c60055",
                        },
                    },
                    "@keyframes sparkle": {
                        "0%": {
                            transform: "scale(0) rotate(0deg)",
                            opacity: 0,
                        },
                        "50%": {
                            transform: "scale(1) rotate(180deg)",
                            opacity: 1,
                        },
                        "100%": {
                            transform: "scale(0) rotate(360deg)",
                            opacity: 0,
                        },
                    },
                    "& .MuiButton-root::after": {
                        content: '""',
                        position: "absolute",
                        width: "20px",
                        height: "20px",
                        background: "radial-gradient(circle, rgba(255,255,255,0.8) 0%, rgba(255,255,255,0) 70%)",
                        top: "-5px",
                        right: "-5px",
                        borderRadius: "50%",
                        animation: "sparkle 3s infinite",
                        animationDelay: "calc(var(--index, 0) * 0.5s)",
                    },
                    "& a": {
                        color: "#c60055",
                        textDecoration: "none",
                        position: "relative",
                        "&::after": {
                            content: '""',
                            position: "absolute",
                            width: "100%",
                            transform: "scaleX(0)",
                            height: "2px",
                            bottom: 0,
                            left: 0,
                            background: "linear-gradient(to right, #ff4d8d, #d176e1)",
                            transformOrigin: "bottom right",
                            transition: "transform 0.3s ease-out",
                        },
                        "&:hover::after": {
                            transform: "scaleX(1)",
                            transformOrigin: "bottom left",
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
                        padding: "8px 16px 16px",
                    },
                    "& .MuiDialogContent-root": {
                        padding: "20px",
                    },
                    "& .MuiDialogActions-root": {
                        padding: "10px 16px 16px",
                    },
                    "& .MuiListItem-root": {
                        paddingTop: "8px",
                        paddingBottom: "8px",
                        transition: "background-color 0.2s ease",
                        "&:hover": {
                            backgroundColor: "rgba(255, 128, 171, 0.08)",
                        },
                    },
                },
            },
            MuiSwitch: {
                styleOverrides: {
                    root: {
                        width: 42,
                        height: 26,
                        padding: 0,
                    },
                    switchBase: {
                        padding: 1,
                        "&.Mui-checked": {
                            transform: "translateX(16px)",
                            color: "#fff",
                            "& + .MuiSwitch-track": {
                                opacity: 1,
                                background: "linear-gradient(45deg, #ff4d8d 30%, #d176e1 90%)",
                            },
                        },
                    },
                    thumb: {
                        width: 24,
                        height: 24,
                    },
                    track: {
                        borderRadius: 13,
                        opacity: 1,
                        backgroundColor: "#f5f5f5",
                        border: "1px solid rgba(255, 77, 141, 0.3)",
                    },
                },
            },
        },
    });

export const pinkTheme: ThemeOption = {
    id: "pink",
    name: "Pink",
    isDark: false,
    getTheme: getPinkTheme,
    hidden: true,
    password: "pinkkk",
};
