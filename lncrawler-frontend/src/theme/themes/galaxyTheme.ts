import { createTheme } from "@mui/material";
import { ThemeOption } from "../types";

export const getGalaxyTheme = () =>
    createTheme({
        palette: {
            mode: "dark",
            primary: {
                main: "#8E24AA", // Purple
                light: "#AB47BC",
                dark: "#6A1B9A",
                contrastText: "#ffffff",
            },
            secondary: {
                main: "#00BCD4", // Cyan
                light: "#4DD0E1",
                dark: "#0097A7",
                contrastText: "#ffffff",
            },
            background: {
                default: "#0F1114", // Near black
                paper: "#1A1D23", // Very dark blue-gray
            },
            text: {
                primary: "#E0E0FF",
                secondary: "#B0B0D0",
            },
            error: {
                main: "#F44336", // Red
                light: "#EF5350",
                dark: "#C62828",
            },
            success: {
                main: "#2ECC71", // Green
                light: "#4CD680",
                dark: "#1EA362",
            },
            info: {
                main: "#29B6F6", // Blue
                light: "#4FC3F7",
                dark: "#0288D1",
            },
            warning: {
                main: "#FFB74D", // Amber
                light: "#FFCC80",
                dark: "#FF9800",
            },
        },
        typography: {
            fontFamily: '"Orbitron", "Roboto", sans-serif',
            fontSize: 16,
            h1: {
                fontFamily: '"Orbitron", sans-serif',
                background: "linear-gradient(45deg, #9C27B0, #3F51B5, #00BCD4, #673AB7)",
                backgroundClip: "text",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                fontWeight: 700,
                fontSize: "3rem",
                textShadow: "0 0 10px rgba(157, 80, 255, 0.4)",
            },
            h2: {
                fontFamily: '"Orbitron", sans-serif',
                background: "linear-gradient(45deg, #9C27B0, #3F51B5, #00BCD4, #673AB7)",
                backgroundClip: "text",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                fontWeight: 700,
                fontSize: "2.5rem",
            },
            h3: {
                fontWeight: 600,
                fontSize: "2rem",
                color: "#9C27B0",
            },
            h4: {
                fontWeight: 600,
                fontSize: "1.8rem",
                color: "#3F51B5",
            },
            h5: {
                fontWeight: 600,
                fontSize: "1.5rem",
                color: "#00BCD4",
            },
            h6: {
                fontWeight: 600,
                fontSize: "1.2rem",
                color: "#673AB7",
            },
            body1: {
                fontSize: "1.1rem",
                letterSpacing: "0.05em",
            },
            body2: {
                fontSize: "1rem",
                letterSpacing: "0.03em",
            },
        },
        shape: {
            borderRadius: 12,
        },
        components: {
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 24,
                        textTransform: "none",
                        padding: "10px 20px",
                        fontWeight: 600,
                        background: "linear-gradient(45deg, #9C27B0, #3F51B5, #00BCD4, #673AB7)",
                        backgroundSize: "300% 300%",
                        animation: "cosmos 15s ease infinite",
                        color: "white",
                        boxShadow: "0 4px 15px rgba(157, 80, 255, 0.3)",
                        transition: "all 0.3s ease",
                        border: "none",
                        "&:hover": {
                            transform: "translateY(-3px) scale(1.05)",
                            boxShadow: "0 7px 20px rgba(157, 80, 255, 0.5), 0 0 20px rgba(157, 80, 255, 0.3)",
                        },
                    },
                },
            },
            MuiCard: {
                styleOverrides: {
                    root: {
                        borderRadius: 16,
                        boxShadow: "0 8px 25px rgba(0,0,0,0.4), inset 0 0 50px rgba(157, 80, 255, 0.1)",
                        overflow: "hidden",
                        position: "relative",
                        transition: "all 0.3s ease",
                        background: "linear-gradient(135deg, rgba(26,29,35,0.95), rgba(15,17,20,0.95))",
                        backdropFilter: "blur(10px)",
                        "&:hover": {
                            transform: "translateY(-5px)",
                            boxShadow: "0 15px 35px rgba(0,0,0,0.5), inset 0 0 60px rgba(157, 80, 255, 0.2)",
                        },
                        "&::before": {
                            content: '""',
                            position: "absolute",
                            top: 0,
                            left: 0,
                            width: "100%",
                            height: "3px",
                            background: "linear-gradient(90deg, #9C27B0, #3F51B5, #00BCD4, #673AB7)",
                            backgroundSize: "300% 300%",
                            animation: "cosmos 15s ease infinite",
                        },
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                        borderRadius: 16,
                        backgroundColor: "rgba(26, 29, 35, 0.8)",
                        backdropFilter: "blur(10px)",
                        position: "relative",
                    },
                    elevation1: {
                        boxShadow: "0 5px 15px rgba(0,0,0,0.3), 0 0 10px rgba(157, 80, 255, 0.1)",
                    },
                    elevation2: {
                        boxShadow: "0 8px 20px rgba(0,0,0,0.4), 0 0 15px rgba(157, 80, 255, 0.2)",
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 20,
                        fontWeight: 600,
                        background: "linear-gradient(45deg, #9C27B0, #3F51B5, #00BCD4, #673AB7)",
                        backgroundSize: "300% 300%",
                        animation: "cosmos 15s ease infinite",
                        color: "white",
                        boxShadow: "0 2px 5px rgba(157, 80, 255, 0.3)",
                    },
                },
            },
            MuiCssBaseline: {
                styleOverrides: {
                    "@keyframes cosmos": {
                        "0%": {
                            backgroundPosition: "0% 50%"
                        },
                        "50%": {
                            backgroundPosition: "100% 50%"
                        },
                        "100%": {
                            backgroundPosition: "0% 50%"
                        }
                    },
                    "@keyframes twinkle": {
                        "0%": {
                            opacity: 0.3,
                            transform: "scale(0.8)"
                        },
                        "50%": {
                            opacity: 1,
                            transform: "scale(1.2)"
                        },
                        "100%": {
                            opacity: 0.3,
                            transform: "scale(0.8)"
                        }
                    },
                    "@keyframes orbit": {
                        "0%": {
                            transform: "translateY(0px) rotate(0deg)"
                        },
                        "50%": {
                            transform: "translateY(-10px) rotate(180deg)"
                        },
                        "100%": {
                            transform: "translateY(0px) rotate(360deg)"
                        }
                    },
                    body: {
                        background: "radial-gradient(ellipse at bottom, #1B2735 0%, #090A0F 100%)",
                        position: "relative",
                        scrollbarWidth: "thin",
                        scrollbarColor: "#9C27B0 #0F1114",
                        "&::-webkit-scrollbar": {
                            width: "8px",
                            height: "8px",
                        },
                        "&::-webkit-scrollbar-track": {
                            background: "#0F1114",
                            borderRadius: "10px",
                        },
                        "&::-webkit-scrollbar-thumb": {
                            background: "linear-gradient(180deg, #9C27B0, #3F51B5, #00BCD4, #673AB7)",
                            borderRadius: "10px",
                            "&:hover": {
                                background: "linear-gradient(180deg, #673AB7, #00BCD4, #3F51B5, #9C27B0)",
                            },
                        },
                        "&::after": {
                            content: '"🌠"',
                            position: "fixed",
                            bottom: "20px",
                            right: "20px",
                            fontSize: "40px",
                            zIndex: 9999,
                            animation: "orbit 7s ease infinite",
                            filter: "drop-shadow(0 0 15px rgba(157, 80, 255, 0.7))",
                            cursor: "pointer",
                        },
                    },
                },
            },
        },
    });

export const galaxyTheme: ThemeOption = {
    id: "galaxy",
    name: "Galaxy",
    isDark: true,
    getTheme: getGalaxyTheme,
    hidden: true,
    password: "cosmos",
    font: {
        family: '"Orbitron", "Roboto", sans-serif',
        url: "https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700&display=swap"
    }
};
