import { createTheme } from "@mui/material";
import { ThemeOption } from "../types";

export const getWindows98Theme = () =>
    createTheme({
        palette: {
            mode: "light",
            primary: {
                main: "#000080", // Classic Windows blue
                light: "#1084d0",
                dark: "#000066",
                contrastText: "#ffffff",
            },
            secondary: {
                main: "#008080", // Teal
                light: "#00a0a0",
                dark: "#006060",
                contrastText: "#ffffff",
            },
            background: {
                default: "#c0c0c0", // Classic Win98 gray
                paper: "#ffffff",
            },
            text: {
                primary: "#000000",
                secondary: "#444444",
            },
            error: {
                main: "#ff0000",
                light: "#ff3333",
                dark: "#cc0000",
            },
            success: {
                main: "#008000",
                light: "#33a033",
                dark: "#006000",
            },
            info: {
                main: "#000080",
                light: "#0000aa",
                dark: "#000066",
            },
            warning: {
                main: "#ffa500",
                light: "#ffb733",
                dark: "#cc8400",
            },
        },
        typography: {
            fontFamily: '"VT323", "Tahoma", Arial, sans-serif',
            fontSize: 15,
            fontWeightLight: 400,
            h1: {
                fontFamily: '"VT323", "Tahoma", Arial, sans-serif',
                fontWeight: 700,
                fontSize: "2.5rem",
            },
            h2: {
                fontFamily: '"VT323", "Tahoma", Arial, sans-serif',
                fontWeight: 700,
                fontSize: "2rem",
            },
            h3: {
                fontFamily: '"VT323", "Tahoma", Arial, sans-serif',
                fontWeight: 600,
                fontSize: "1.7rem",
            },
            h4: {
                fontFamily: '"VT323", "Tahoma", Arial, sans-serif',
                fontWeight: 600,
                fontSize: "1.5rem",
            },
            h5: {
                fontWeight: 600,
                fontSize: "1.4rem",
            },
            h6: {
                fontWeight: 600,
                fontSize: "1.3rem",
            },
            body1: {
                lineHeight: 1.5,
                fontSize: "1.2rem",
            },
            body2: {
                lineHeight: 1.5,
                fontSize: "1.1rem",
            },
        },
        shape: {
            borderRadius: 0, // Windows 98 had sharp edges
        },
        components: {
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 0,
                        textTransform: "none",
                        padding: "2px 10px",
                        minWidth: "75px",
                        boxShadow: "inset -1px -1px #0a0a0a, inset 1px 1px #ffffff, inset -2px -2px grey, inset 2px 2px #dfdfdf",
                        fontWeight: 400,
                        "&:active": {
                            boxShadow: "inset -1px -1px #ffffff, inset 1px 1px #0a0a0a, inset -2px -2px #dfdfdf, inset 2px 2px grey",
                        },
                    },
                    containedPrimary: {
                        backgroundColor: "#c0c0c0",
                        color: "#000000",
                        "&:hover": {
                            backgroundColor: "#d0d0d0",
                        },
                    },
                    outlinedPrimary: {
                        borderWidth: 1,
                    },
                },
            },
            MuiCard: {
                styleOverrides: {
                    root: {
                        borderRadius: 0,
                        boxShadow: "inset -1px -1px #0a0a0a, inset 1px 1px #ffffff, inset -2px -2px grey, inset 2px 2px #dfdfdf",
                        backgroundColor: "#c0c0c0",
                    },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: {
                        backgroundColor: "#000080",
                        boxShadow: "inset -1px -1px #0a0a0a, inset 1px 1px #ffffff, inset -2px -2px grey, inset 2px 2px #dfdfdf",
                        "& .MuiTypography-root": {
                            color: "#ffffff",
                        },
                    },
                },
            },
            MuiToolbar: {
                styleOverrides: {
                    root: {
                        backgroundColor: "#000080",
                        boxShadow: "inset -1px -1px #0a0a0a, inset 1px 1px #ffffff, inset -2px -2px grey, inset 2px 2px #dfdfdf",
                        "& .MuiTypography-root": {
                            color: "#ffffff",
                        },
                        "& .MuiIconButton-root": {
                            color: "#ffffff",
                            "&:hover": {
                                backgroundColor: "rgba(255, 255, 255, 0.1)",
                            },
                        },
                        "& .MuiSvgIcon-root": {
                            color: "#ffffff",
                        },
                        "& img": {
                            filter: "invert(1)",
                        },
                        "& .MuiButtonBase-root": {
                            color: "#ffffff",
                        },
                    },
                },
            },
            MuiDivider: {
                styleOverrides: {
                    root: {
                        borderColor: "#808080",
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                        backgroundColor: "#c0c0c0",
                        border: "1px solid #808080",
                        boxShadow: "inset -1px -1px #0a0a0a, inset 1px 1px #ffffff, inset -2px -2px grey, inset 2px 2px #dfdfdf",
                    },
                    elevation1: {
                        boxShadow: "inset -1px -1px #0a0a0a, inset 1px 1px #ffffff, inset -2px -2px grey, inset 2px 2px #dfdfdf",
                    },
                    elevation2: {
                        boxShadow: "inset -1px -1px #0a0a0a, inset 1px 1px #ffffff, inset -2px -2px grey, inset 2px 2px #dfdfdf",
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 0,
                        fontWeight: 400,
                        boxShadow: "inset -1px -1px #0a0a0a, inset 1px 1px #ffffff, inset -2px -2px grey, inset 2px 2px #dfdfdf",
                    },
                },
            },
            MuiTextField: {
                styleOverrides: {
                    root: {
                        "& .MuiOutlinedInput-root": {
                            borderRadius: 0,
                            boxShadow: "inset -1px -1px #ffffff, inset 1px 1px #0a0a0a, inset -2px -2px #dfdfdf, inset 2px 2px grey",
                        },
                    },
                },
            },
            MuiCssBaseline: {
                styleOverrides: {
                    body: {
                        scrollbarWidth: "thin",
                        scrollbarColor: "#c0c0c0 #ffffff",
                        "&::-webkit-scrollbar": {
                            width: "16px",
                            height: "16px",
                        },
                        "&::-webkit-scrollbar-track": {
                            background: "#c0c0c0",
                            border: "1px solid #808080",
                        },
                        "&::-webkit-scrollbar-thumb": {
                            background: "#c0c0c0",
                            borderRadius: 0,
                            boxShadow: "inset -1px -1px #0a0a0a, inset 1px 1px #ffffff, inset -2px -2px grey, inset 2px 2px #dfdfdf",
                        },
                    },
                    "& .MuiContainer-root": {
                        paddingLeft: "10px",
                        paddingRight: "10px",
                    },
                    "& .MuiCardContent-root": {
                        padding: "10px",
                        "&:last-child": {
                            paddingBottom: "10px",
                        },
                    },
                    "& .MuiCardActions-root": {
                        padding: "6px 10px",
                    },
                    "& .MuiDialogContent-root": {
                        padding: "10px",
                    },
                    "& .MuiDialogActions-root": {
                        padding: "6px 10px",
                    },
                    "& .MuiListItem-root": {
                        paddingTop: "4px",
                        paddingBottom: "4px",
                    },
                },
            },
        },
    });

export const windows98Theme: ThemeOption = {
    id: "windows98",
    name: "Windows 98",
    isDark: false,
    getTheme: getWindows98Theme,
    hidden: true,
    password: "clippy",
    font: {
        family: '"VT323", "Tahoma", Arial, sans-serif',
        // MS Sans Serif isn't on Google Fonts, so we'll use something similar like VT323
        url: "https://fonts.googleapis.com/css2?family=VT323&display=swap"
    }
};
