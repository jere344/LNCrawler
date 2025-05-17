import { createTheme } from "@mui/material";
import { ThemeOption } from "../types";

const Flag =
    "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA1IDMiPjxyZWN0IHdpZHRoPSI1IiBoZWlnaHQ9IjMiIGZpbGw9IiNmZmYiLz48cmVjdCB3aWR0aD0iNSIgaGVpZ2h0PSIwLjYiIGZpbGw9IiM1QkNFRkEiLz48cmVjdCB3aWR0aD0iNSIgaGVpZ2h0PSIwLjYiIHk9IjAuNiIgZmlsbD0iI0Y1QTlCOCIvPjxyZWN0IHdpZHRoPSI1IiBoZWlnaHQ9IjAuNiIgeT0iMS44IiBmaWxsPSIjRjVBOUI4Ii8+PHJlY3Qgd2lkdGg9IjUiIGhlaWdodD0iMC42IiB5PSIyLjQiIGZpbGw9IiM1QkNFRkEiLz48L3N2Zz4=";

export const getTransTheme = () =>
    createTheme({
        palette: {
            mode: "light",
            primary: {
                main: "#F5A9B8",
                light: "#FFCAD4",
                dark: "#D1899D",
                contrastText: "#000000",
            },
            secondary: {
                main: "#5BCEFA",
                light: "#8DDBFF",
                dark: "#36A6D1",
                contrastText: "#000000",
            },
            background: {
                default: "#FFF9FB",
                paper: "#FFFFFF",
            },
            text: {
                primary: "#333333",
                secondary: "#5D5D5D",
            },
            error: {
                main: "#FF5252",
                light: "#FF7A7A",
                dark: "#D32F2F",
            },
            success: {
                main: "#4CAF50",
                light: "#7BC67E",
                dark: "#3B873E",
            },
            info: {
                main: "#5BCEFA",
                light: "#8DDBFF",
                dark: "#36A6D1",
            },
            warning: {
                main: "#FFC107",
                light: "#FFD54F",
                dark: "#FFA000",
            },
        },
        typography: {
            fontFamily: '"Quicksand", "Roboto", "Helvetica", "Arial", sans-serif',
            fontSize: 14,
            h1: {
                fontFamily: '"Quicksand", sans-serif',
                fontWeight: 700,
                fontSize: "2.2rem",
                background:
                    "linear-gradient(90deg, #5BCEFA 0%, #5BCEFA 45%, #FFFFFF 50%, #F5A9B8 55%, #F5A9B8 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
            },
            h2: {
                fontFamily: '"Quicksand", sans-serif',
                fontWeight: 700,
                fontSize: "1.9rem",
                color: "#F5A9B8", // Changed to pink
            },
            h3: {
                fontFamily: '"Quicksand", sans-serif',
                fontWeight: 600,
                fontSize: "1.6rem",
                color: "#5BCEFA", // Changed to blue
            },
            h4: {
                fontFamily: '"Quicksand", sans-serif',
                fontWeight: 600,
                fontSize: "1.4rem",
                color: "#F5A9B8", // Added pink color
            },
            h5: {
                fontWeight: 600,
                fontSize: "1.2rem",
                color: "#5BCEFA", // Added blue color
            },
            h6: {
                fontWeight: 600,
                fontSize: "1.05rem",
                color: "#F5A9B8", // Added pink color
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
            borderRadius: 12, // Soft rounded edges
        },
        components: {
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 8,
                        textTransform: "none",
                        padding: "8px 18px",
                        fontSize: "0.95rem",
                        fontWeight: 600,
                        transition: "all 0.2s ease-in-out",
                    },
                    containedPrimary: {
                        background: "linear-gradient(135deg, #F5A9B8 0%, #D1899D 100%)",
                        "&:hover": {
                            background: "linear-gradient(135deg, #D1899D 0%, #F5A9B8 100%)",
                            transform: "translateY(-2px)",
                            boxShadow: "0 6px 10px rgba(245, 169, 184, 0.3)",
                        },
                    },
                    containedSecondary: {
                        background: "linear-gradient(135deg, #5BCEFA 0%, #36A6D1 100%)",
                        "&:hover": {
                            background: "linear-gradient(135deg, #36A6D1 0%, #5BCEFA 100%)",
                            transform: "translateY(-2px)",
                            boxShadow: "0 6px 10px rgba(91, 206, 250, 0.3)",
                        },
                    },
                    outlinedPrimary: {
                        borderWidth: 2,
                        "&:hover": {
                            borderWidth: 2,
                            boxShadow: "0 4px 8px rgba(245, 169, 184, 0.2)",
                        },
                    },
                    outlinedSecondary: {
                        borderWidth: 2,
                        "&:hover": {
                            borderWidth: 2,
                            boxShadow: "0 4px 8px rgba(91, 206, 250, 0.2)",
                        },
                    },
                },
            },
            MuiCard: {
                styleOverrides: {
                    root: {
                        borderRadius: 12,
                        boxShadow: "0 5px 15px rgba(0, 0, 0, 0.08)",
                        overflow: "hidden",
                        transition: "transform 0.3s ease, box-shadow 0.3s ease",
                        "&:hover": {
                            boxShadow: "0 8px 25px rgba(0, 0, 0, 0.12)",
                            transform: "translateY(-4px)",
                        },
                        "&::before": {
                            content: '""',
                            position: "absolute",
                            top: 0,
                            left: 0,
                            right: 0,
                            height: "4px",
                            background:
                                "linear-gradient(90deg, #5BCEFA 0%, #FFFFFF 50%, #F5A9B8 100%)",
                        }
                    },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: {
                        background: "rgba(255, 255, 255, 0.9)",
                        backdropFilter: "blur(10px)",
                        boxShadow: "0 2px 10px rgba(0, 0, 0, 0.05)",
                        borderBottom: "1px solid rgba(0, 0, 0, 0.05)",
                        "&::after": {
                            content: '""',
                            position: "absolute",
                            bottom: 0,
                            left: 0,
                            right: 0,
                            height: "2px",
                            background:
                                "linear-gradient(90deg, #5BCEFA 0%, #FFFFFF 50%, #F5A9B8 100%)",
                        },
                    },
                },
            },
            MuiDivider: {
                styleOverrides: {
                    root: {
                        background: "linear-gradient(90deg, #5BCEFA 0%, #FFFFFF 50%, #F5A9B8 100%)",
                        height: "2px",
                        opacity: 0.7,
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        borderRadius: 12,
                    },
                    elevation1: {
                        boxShadow: "0 2px 8px rgba(0, 0, 0, 0.06)",
                    },
                    elevation2: {
                        boxShadow: "0 3px 10px rgba(0, 0, 0, 0.08)",
                    },
                    elevation3: {
                        boxShadow: "0 5px 15px rgba(0, 0, 0, 0.1)",
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 16,
                        fontWeight: 500,
                        "& .MuiChip-label": {
                            padding: "0 12px",
                        },
                    },
                    colorPrimary: {
                        background: "linear-gradient(90deg, #F5A9B8 0%, #D1899D 100%)",
                    },
                    colorSecondary: {
                        background: "linear-gradient(90deg, #5BCEFA 0%, #36A6D1 100%)",
                    },
                },
            },
            MuiCssBaseline: {
                styleOverrides: {
                    body: {
                        scrollbarWidth: "thin",
                        scrollbarColor: "#F5A9B8 #F5F5F5",
                        "&::-webkit-scrollbar": {
                            width: "8px",
                            height: "8px",
                        },
                        "&::-webkit-scrollbar-track": {
                            background: "#F5F5F5",
                        },
                        "&::-webkit-scrollbar-thumb": {
                            background: "linear-gradient(180deg, #5BCEFA, #FFFFFF, #F5A9B8)",
                            borderRadius: "4px",
                        },
                        "&::-webkit-scrollbar-thumb:hover": {
                            background: "linear-gradient(180deg, #36A6D1, #FFFFFF, #D1899D)",
                        },
                        "&::before": {
                            content: '""',
                            position: "fixed",
                            top: 0,
                            right: 0,
                            width: "60px",
                            height: "36px",
                            backgroundImage: `url(${Flag})`,
                            backgroundSize: "contain",
                            backgroundRepeat: "no-repeat",
                            opacity: 0.2,
                            zIndex: 9999,
                            pointerEvents: "none",
                            margin: "8px",
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
                        padding: "12px 16px",
                    },
                    "& .MuiInputBase-root": {
                        "&.Mui-focused::before": {
                            borderImage: "linear-gradient(90deg, #5BCEFA, #FFFFFF, #F5A9B8) 1",
                            borderWidth: "2px",
                        },
                    },
                    "& .MuiLink-root": {
                        background: "linear-gradient(90deg, #F5A9B8, #5BCEFA)",
                        WebkitBackgroundClip: "text",
                        WebkitTextFillColor: "transparent",
                        fontWeight: 600,
                    },
                },
            },
            MuiListItem: {
                styleOverrides: {
                    root: {
                        "&.Mui-selected": {
                            backgroundColor: "rgba(245, 169, 184, 0.15)",
                            "&:hover": {
                                backgroundColor: "rgba(245, 169, 184, 0.25)",
                            },
                            "&::before": {
                                content: '""',
                                position: "absolute",
                                left: 0,
                                top: 0,
                                bottom: 0,
                                width: "4px",
                                background: "linear-gradient(180deg, #5BCEFA, #FFFFFF, #F5A9B8)",
                            },
                        },
                    },
                },
            },
            MuiSwitch: {
                styleOverrides: {
                    switchBase: {
                        "&.Mui-checked": {
                            color: "#F5A9B8",
                            "& + .MuiSwitch-track": {
                                backgroundColor: "#5BCEFA",
                                opacity: 0.9,
                            },
                        },
                    },
                    track: {
                        backgroundColor: "#D1899D",
                        opacity: 0.5,
                    },
                    thumb: {
                        boxShadow: "0 2px 4px 0 rgba(0, 0, 0, 0.2)",
                    },
                },
            },
        },
    });

export const tfTheme: ThemeOption = {
    id: "tf",
    name: "TF",
    isDark: false,
    getTheme: getTransTheme,
    hidden: true,
    password: "blahaj",
};
