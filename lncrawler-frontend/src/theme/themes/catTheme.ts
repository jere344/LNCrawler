import { createTheme } from "@mui/material";
import { ThemeOption } from "../types";
import catSvg from "./svg/cat.svg";

export const getCatTheme = () =>
    createTheme({
        palette: {
            mode: "light",
            primary: {
                main: "#FF6B6B", 
                light: "#FF9E9E",
                dark: "#CC5555",
                contrastText: "#ffffff",
            },
            secondary: {
                main: "#4ECDC4",
                light: "#7EDEDB",
                dark: "#37A59E",
                contrastText: "#ffffff",
            },
            background: {
                default: "#FFF1E6",
                paper: "#ffffff",
            },
            text: {
                primary: "#594A4E",
                secondary: "#7A6C70",
            },
            error: {
                main: "#F25F5C",
                light: "#F58482",
                dark: "#C14C4A",
            },
            success: {
                main: "#70C1B3",
                light: "#A2D7CE",
                dark: "#50A194",
            },
            info: {
                main: "#50B2C0",
                light: "#7CCAD6",
                dark: "#3A8A95",
            },
            warning: {
                main: "#FFD166",
                light: "#FFDF94",
                dark: "#D1A94E",
            },
        },
        typography: {
            fontFamily: '"Nunito", "Comic Sans MS", Arial, sans-serif',
            fontSize: 14,
            fontWeightLight: 400,
            h1: {
                fontFamily: '"Nunito", "Comic Sans MS", Arial, sans-serif',
                fontWeight: 700,
                fontSize: "2.5rem",
            },
            h2: {
                fontFamily: '"Nunito", "Comic Sans MS", Arial, sans-serif',
                fontWeight: 700,
                fontSize: "2rem",
            },
            h3: {
                fontFamily: '"Nunito", "Comic Sans MS", Arial, sans-serif',
                fontWeight: 600,
                fontSize: "1.8rem",
            },
            h4: {
                fontFamily: '"Nunito", "Comic Sans MS", Arial, sans-serif',
                fontWeight: 600,
                fontSize: "1.5rem",
            },
            h5: {
                fontWeight: 600,
                fontSize: "1.3rem",
            },
            h6: {
                fontWeight: 600,
                fontSize: "1.1rem",
            },
            body1: {
                fontSize: "1.1rem",
            },
            body2: {
                fontSize: "1rem",
            },
        },
        shape: {
            borderRadius: 12,
        },
        components: {
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 20,
                        textTransform: "none",
                        padding: "8px 16px",
                        fontWeight: 600,
                        boxShadow: "0 4px 8px rgba(0,0,0,0.1)",
                        transition: "all 0.3s ease",
                        "&:hover": {
                            transform: "translateY(-2px)",
                            boxShadow: "0 6px 12px rgba(0,0,0,0.15)",
                        },
                    },
                },
            },
            MuiCard: {
                styleOverrides: {
                    root: {
                        borderRadius: 16,
                        boxShadow: "0 8px 16px rgba(0,0,0,0.1)",
                        overflow: "hidden",
                        transition: "all 0.3s ease",
                        "&:hover": {
                            boxShadow: "0 12px 24px rgba(0,0,0,0.15)",
                            transform: "translateY(-4px)",
                        },
                        "&::before": {
                            content: '""',
                            position: "absolute",
                            top: 0,
                            left: 0,
                            width: "100%",
                            height: "5px",
                            background: "linear-gradient(90deg, #FF6B6B, #4ECDC4)",
                        },
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                        borderRadius: 12,
                    },
                    elevation1: {
                        boxShadow: "0 4px 8px rgba(0,0,0,0.1)",
                    },
                    elevation2: {
                        boxShadow: "0 6px 12px rgba(0,0,0,0.1)",
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 16,
                        fontWeight: 500,
                        "&::after": {
                            content: '""',
                            display: "inline-block",
                            width: "8px",
                            height: "8px",
                            borderRadius: "50%",
                            marginLeft: "8px",
                        },
                    },
                },
            },
            MuiCssBaseline: {
                styleOverrides: {
                    body: {
                        scrollbarWidth: "thin",
                        scrollbarColor: "#FF6B6B #FFF1E6",
                        "&::-webkit-scrollbar": {
                            width: "8px",
                            height: "8px",
                        },
                        "&::-webkit-scrollbar-track": {
                            background: "#FFF1E6",
                            borderRadius: "10px",
                        },
                        "&::-webkit-scrollbar-thumb": {
                            background: "#FF6B6B",
                            borderRadius: "10px",
                            "&:hover": {
                                background: "#FF9E9E",
                            },
                        },
                        "&::after": {
                            content: '""',
                            position: "fixed",
                            bottom: "20px",
                            right: "20px",
                            width: "50px",
                            height: "50px",
                            backgroundImage: `url(${catSvg})`,
                            backgroundSize: "contain",
                            backgroundRepeat: "no-repeat",
                            zIndex: 9999,
                            opacity: 0.7,
                            cursor: "pointer",
                            animation: "bounce 2s infinite",
                        },
                        "@keyframes bounce": {
                            "0%, 100%": {
                                transform: "translateY(0)",
                            },
                            "50%": {
                                transform: "translateY(-10px)",
                            },
                        },
                    },
                },
            },
        },
    });

export const catTheme: ThemeOption = {
    id: "cat",
    name: "Feline",
    isDark: false,
    getTheme: getCatTheme,
    hidden: true,
    password: "Orion",
    font: {
        family: '"Nunito", "Comic Sans MS", Arial, sans-serif',
        url: "https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700&display=swap"
    }
};
