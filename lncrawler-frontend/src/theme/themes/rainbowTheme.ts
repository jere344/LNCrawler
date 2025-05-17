import { createTheme } from "@mui/material";
import { ThemeOption } from "../types";

export const getRainbowTheme = () =>
    createTheme({
        palette: {
            mode: "light",
            primary: {
                main: "#FF1493", // Hot pink
                light: "#FF69B4",
                dark: "#C71585",
                contrastText: "#ffffff",
            },
            secondary: {
                main: "#00BFFF", // Deep sky blue
                light: "#87CEFA",
                dark: "#1E90FF",
                contrastText: "#ffffff",
            },
            background: {
                default: "#F9F9F9",
                paper: "#ffffff",
            },
            text: {
                primary: "#333333",
                secondary: "#666666",
            },
            error: {
                main: "#FF4500", // OrangeRed
                light: "#FF6347",
                dark: "#DC143C",
            },
            success: {
                main: "#32CD32", // LimeGreen
                light: "#90EE90",
                dark: "#008000",
            },
            info: {
                main: "#9370DB", // MediumPurple
                light: "#B19CD9",
                dark: "#6A5ACD",
            },
            warning: {
                main: "#FFD700", // Gold
                light: "#FFFF00",
                dark: "#FFA500",
            },
        },
        typography: {
            fontFamily: '"Pacifico", "Comic Sans MS", cursive',
            fontSize: 16,
            h1: {
                fontFamily: '"Pacifico", cursive',
                background: "linear-gradient(45deg, #FF0000, #FF7F00, #FFFF00, #00FF00, #0000FF, #4B0082, #9400D3)",
                backgroundClip: "text",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                fontWeight: 700,
                fontSize: "3rem",
                textShadow: "1px 1px 2px rgba(0,0,0,0.1)",
            },
            h2: {
                fontFamily: '"Pacifico", cursive',
                background: "linear-gradient(45deg, #FF0000, #FF7F00, #FFFF00, #00FF00, #0000FF, #4B0082, #9400D3)",
                backgroundClip: "text",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                fontWeight: 700,
                fontSize: "2.5rem",
            },
            h3: {
                fontWeight: 600,
                fontSize: "2rem",
                color: "#FF1493",
            },
            h4: {
                fontWeight: 600,
                fontSize: "1.8rem",
                color: "#00BFFF",
            },
            h5: {
                fontWeight: 600,
                fontSize: "1.5rem",
                color: "#32CD32",
            },
            h6: {
                fontWeight: 600,
                fontSize: "1.2rem",
                color: "#9370DB",
            },
            body1: {
                fontSize: "1.1rem",
            },
            body2: {
                fontSize: "1rem",
            },
        },
        shape: {
            borderRadius: 20,
        },
        components: {
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 30,
                        textTransform: "none",
                        padding: "10px 20px",
                        fontWeight: 600,
                        background: "linear-gradient(45deg, #FF0000, #FF7F00, #FFFF00, #00FF00, #0000FF, #4B0082, #9400D3)",
                        backgroundSize: "400% 400%",
                        animation: "rainbow 10s ease infinite",
                        color: "white",
                        boxShadow: "0 4px 15px rgba(0,0,0,0.2)",
                        transition: "all 0.3s ease",
                        border: "none",
                        "&:hover": {
                            transform: "translateY(-3px) scale(1.05)",
                            boxShadow: "0 7px 20px rgba(0,0,0,0.25)",
                        },
                    },
                },
            },
            MuiCard: {
                styleOverrides: {
                    root: {
                        borderRadius: 25,
                        boxShadow: "0 8px 25px rgba(0,0,0,0.1)",
                        overflow: "hidden",
                        position: "relative",
                        transition: "all 0.3s ease",
                        "&:hover": {
                            transform: "translateY(-5px)",
                            boxShadow: "0 15px 35px rgba(0,0,0,0.2)",
                        },
                        "&::before": {
                            content: '""',
                            position: "absolute",
                            top: 0,
                            left: 0,
                            width: "100%",
                            height: "8px",
                            background: "linear-gradient(90deg, #FF0000, #FF7F00, #FFFF00, #00FF00, #0000FF, #4B0082, #9400D3)",
                            backgroundSize: "400% 400%",
                            animation: "rainbow 10s ease infinite",
                        },
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                        borderRadius: 15,
                    },
                    elevation1: {
                        boxShadow: "0 5px 15px rgba(0,0,0,0.08)",
                    },
                    elevation2: {
                        boxShadow: "0 8px 20px rgba(0,0,0,0.1)",
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 20,
                        fontWeight: 600,
                        background: "linear-gradient(45deg, #FF0000, #FF7F00, #FFFF00, #00FF00, #0000FF, #4B0082, #9400D3)",
                        backgroundSize: "400% 400%",
                        animation: "rainbow 10s ease infinite",
                        color: "white",
                    },
                },
            },
            MuiCssBaseline: {
                styleOverrides: {
                    "@keyframes rainbow": {
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
                    "@keyframes float": {
                        "0%": {
                            transform: "translateY(0px) rotate(0deg)"
                        },
                        "50%": {
                            transform: "translateY(-10px) rotate(5deg)"
                        },
                        "100%": {
                            transform: "translateY(0px) rotate(0deg)"
                        }
                    },
                    body: {
                        background: "linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)",
                        scrollbarWidth: "thin",
                        scrollbarColor: "#FF1493 #F9F9F9",
                        "&::-webkit-scrollbar": {
                            width: "8px",
                            height: "8px",
                        },
                        "&::-webkit-scrollbar-track": {
                            background: "#F9F9F9",
                            borderRadius: "10px",
                        },
                        "&::-webkit-scrollbar-thumb": {
                            background: "linear-gradient(180deg, #FF0000, #FF7F00, #FFFF00, #00FF00, #0000FF, #4B0082, #9400D3)",
                            borderRadius: "10px",
                            "&:hover": {
                                background: "linear-gradient(180deg, #9400D3, #4B0082, #0000FF, #00FF00, #FFFF00, #FF7F00, #FF0000)",
                            },
                        },
                        "&::after": {
                            content: '"🌈"',
                            position: "fixed",
                            bottom: "20px",
                            right: "20px",
                            fontSize: "40px",
                            zIndex: 9999,
                            animation: "float 3s ease infinite",
                            filter: "drop-shadow(0 0 10px rgba(255,255,255,0.7))",
                            cursor: "pointer",
                        },
                    },
                },
            },
        },
    });

export const rainbowTheme: ThemeOption = {
    id: "rainbow",
    name: "Rainbow",
    isDark: false,
    getTheme: getRainbowTheme,
    hidden: true,
    password: "spectrum",
    font: {
        family: '"Pacifico", "Comic Sans MS", cursive',
        url: "https://fonts.googleapis.com/css2?family=Pacifico&display=swap"
    }
};
