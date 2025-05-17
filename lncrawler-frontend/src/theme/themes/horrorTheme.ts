import { createTheme } from "@mui/material";
import { ThemeOption } from "../types";

export const getHorrorTheme = () =>
    createTheme({
        palette: {
            mode: "dark",
            primary: {
                main: "#FF0000", // Blood red
                light: "#FF3333",
                dark: "#990000",
                contrastText: "#ffffff",
            },
            secondary: {
                main: "#8A0303", // Darker blood color
                light: "#A52A2A",
                dark: "#560000",
                contrastText: "#ffffff",
            },
            background: {
                default: "#000000",
                paper: "#111111",
            },
            text: {
                primary: "#ffffff",
                secondary: "#bbbbbb",
            },
            error: {
                main: "#FF0000",
                light: "#FF5252",
                dark: "#C50000",
            },
            success: {
                main: "#00FF00", // Eerie green
                light: "#66FF66",
                dark: "#009900",
            },
            info: {
                main: "#4B0082", // Deep purple
                light: "#8A2BE2",
                dark: "#240041",
            },
            warning: {
                main: "#FFA500", // Jack-o-lantern orange
                light: "#FFCC00",
                dark: "#CC7000",
            },
        },
        typography: {
            fontFamily: '"Nosifer", "Creepster", cursive',
            fontSize: 16,
            h1: {
                fontFamily: '"Nosifer", cursive',
                color: "#FF0000",
                textShadow: "0 0 10px rgba(255, 0, 0, 0.7), 0 0 20px rgba(255, 0, 0, 0.5)",
                letterSpacing: "2px",
                fontWeight: 700,
                fontSize: "3rem",
            },
            h2: {
                fontFamily: '"Nosifer", cursive',
                color: "#FF0000",
                textShadow: "0 0 8px rgba(255, 0, 0, 0.7)",
                letterSpacing: "1.5px",
                fontWeight: 700,
                fontSize: "2.5rem",
            },
            h3: {
                fontFamily: '"Creepster", cursive',
                fontWeight: 600,
                fontSize: "2rem",
                color: "#FF3333",
                textShadow: "0 0 5px rgba(255, 0, 0, 0.5)",
            },
            h4: {
                fontWeight: 600,
                fontSize: "1.8rem",
                color: "#FF3333",
            },
            h5: {
                fontWeight: 600,
                fontSize: "1.5rem",
                color: "#FF3333",
            },
            h6: {
                fontWeight: 600,
                fontSize: "1.2rem",
                color: "#FF3333",
            },
            body1: {
                fontSize: "1.1rem",
                fontFamily: '"Special Elite", serif',
            },
            body2: {
                fontSize: "1rem",
                fontFamily: '"Special Elite", serif',
            },
        },
        shape: {
            borderRadius: 0, // Sharp, jagged edges
        },
        components: {
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 0,
                        textTransform: "uppercase",
                        padding: "10px 20px",
                        fontWeight: 600,
                        fontFamily: '"Creepster", cursive',
                        backgroundColor: "#990000",
                        color: "white",
                        boxShadow: "0 4px 10px rgba(255, 0, 0, 0.3), inset 0 0 5px rgba(0, 0, 0, 0.5)",
                        transition: "all 0.3s ease",
                        border: "1px solid #FF0000",
                        "&:hover": {
                            backgroundColor: "#FF0000",
                            boxShadow: "0 0 15px rgba(255, 0, 0, 0.7), inset 0 0 10px rgba(255, 0, 0, 0.5)",
                            transform: "translateY(-2px) scale(1.02)",
                            borderColor: "#FF3333",
                        },
                        "&:active": {
                            boxShadow: "0 0 5px rgba(255, 0, 0, 0.5)",
                            transform: "translateY(1px)",
                        },
                    },
                },
            },
            MuiCard: {
                styleOverrides: {
                    root: {
                        borderRadius: 0,
                        boxShadow: "0 8px 20px rgba(0, 0, 0, 0.8), 0 0 5px rgba(255, 0, 0, 0.3)",
                        backgroundColor: "#111111",
                        overflow: "hidden",
                        position: "relative",
                        transition: "all 0.3s ease",
                        border: "1px solid #333333",
                        "&:hover": {
                            transform: "translateY(-3px)",
                            boxShadow: "0 12px 30px rgba(0, 0, 0, 0.9), 0 0 8px rgba(255, 0, 0, 0.5)",
                            "& .MuiCardHeader-root": {
                                backgroundPosition: "right center",
                            },
                        },
                        "&::before": {
                            content: '""',
                            position: "absolute",
                            top: 0,
                            left: 0,
                            width: "100%",
                            height: "3px",
                            background: "linear-gradient(90deg, transparent, #FF0000, transparent)",
                            opacity: 0.7,
                        },
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    elevation1: {
                        boxShadow: "0 5px 15px rgba(0, 0, 0, 0.8), 0 0 5px rgba(255, 0, 0, 0.2)",
                    },
                    elevation2: {
                        boxShadow: "0 8px 20px rgba(0, 0, 0, 0.8), 0 0 8px rgba(255, 0, 0, 0.3)",
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 0,
                        fontWeight: 600,
                        backgroundColor: "#333333",
                        color: "#FF0000",
                        border: "1px solid #FF0000",
                        boxShadow: "0 0 5px rgba(255, 0, 0, 0.3)",
                    },
                },
            },
            MuiCssBaseline: {
                styleOverrides: {
                    "@keyframes flicker": {
                        "0%": { opacity: 1 },
                        "5%": { opacity: 0.8 },
                        "10%": { opacity: 1 },
                        "15%": { opacity: 0.9 },
                        "20%": { opacity: 1 },
                        "55%": { opacity: 1 },
                        "60%": { opacity: 0.7 },
                        "65%": { opacity: 1 },
                        "100%": { opacity: 1 },
                    },
                    "@keyframes blood-drip": {
                        "0%": { 
                            height: "0%",
                            opacity: 0,
                        },
                        "50%": {
                            opacity: 0.7,
                        },
                        "100%": { 
                            height: "100%",
                            opacity: 0,
                        },
                    },
                    body: {
                        background: "#000000",
                        animation: "flicker 5s infinite",
                        scrollbarWidth: "thin",
                        scrollbarColor: "#FF0000 #111111",
                        "&::-webkit-scrollbar": {
                            width: "8px",
                            height: "8px",
                        },
                        "&::-webkit-scrollbar-track": {
                            background: "#111111",
                            boxShadow: "inset 0 0 5px rgba(0,0,0,0.5)",
                        },
                        "&::-webkit-scrollbar-thumb": {
                            background: "#FF0000",
                            boxShadow: "0 0 5px rgba(255,0,0,0.5)",
                            "&:hover": {
                                background: "#990000",
                            },
                        },
                        "&::before": {
                            content: '""',
                            position: "fixed",
                            top: 0,
                            right: "10px",
                            width: "2px",
                            height: "0%",
                            background: "linear-gradient(to bottom, transparent, #FF0000, #FF0000, transparent)",
                            animation: "blood-drip 20s infinite",
                            zIndex: 9999,
                            opacity: 0,
                        },
                        "&::after": {
                            content: '"👻"',
                            position: "fixed",
                            bottom: "20px",
                            right: "20px",
                            fontSize: "40px",
                            opacity: "0.3",
                            zIndex: 9999,
                            filter: "drop-shadow(0 0 5px rgba(255,255,255,0.5))",
                            cursor: "pointer",
                        },
                    },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: {
                        background: "#111111",
                        boxShadow: "0 0 10px rgba(255, 0, 0, 0.5)",
                        borderBottom: "1px solid #990000",
                    }
                }
            },
            MuiSwitch: {
                styleOverrides: {
                    switchBase: {
                        color: "#990000",
                        "&.Mui-checked": {
                            color: "#FF0000",
                            "& + .MuiSwitch-track": {
                                backgroundColor: "#990000",
                                opacity: 0.8,
                            },
                        },
                    },
                    track: {
                        backgroundColor: "#333333",
                        opacity: 0.9,
                    },
                    thumb: {
                        boxShadow: "0 0 5px rgba(255, 0, 0, 0.5)",
                    },
                },
            },
        },
    });

export const horrorTheme: ThemeOption = {
    id: "horror",
    name: "Horror",
    isDark: true,
    getTheme: getHorrorTheme,
    hidden: true,
    password: "redrum",
    font: {
        family: '"Nosifer", "Creepster", "Special Elite", cursive',
        url: "https://fonts.googleapis.com/css2?family=Nosifer&family=Creepster&family=Special+Elite&display=swap"
    }
};
