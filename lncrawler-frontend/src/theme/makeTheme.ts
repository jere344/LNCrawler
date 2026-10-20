import { createTheme, PaletteOptions, ThemeOptions } from "@mui/material";

// Values that vary between themes sharing the same component skeleton.
export interface ThemeTokens {
    palette: PaletteOptions;
    typography: ThemeOptions["typography"];
    radius: number;
    button: {
        radius: number;
        brandGradient: string;
        brandGradientHover: string;
        primaryShadow: string;
        primaryHoverShadow: string;
        primaryDisabledColor?: string;
    };
    card: {
        radius: number;
        shadow: string;
        hoverShadow: string;
        background?: string;
        backgroundImage?: string;
        border?: string;
        borderTopLeft?: string;
    };
    appBar: {
        background: string;
        color?: string;
        shadow: string;
    };
    dividerColor: string;
    paperShadows: [string, string, string];
    chipPrimaryColor: string;
    scrollbar: {
        color: string;
        track: string;
        thumb: string;
        thumbHover: string;
    };
    gutterBottomMargin?: string;
}

export const makeTheme = (
    tokens: ThemeTokens,
    extraComponents: NonNullable<ThemeOptions["components"]> = {},
) =>
    createTheme({
        palette: tokens.palette,
        typography: tokens.typography,
        spacing: 8,
        shape: {
            borderRadius: tokens.radius,
        },
        components: {
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius: tokens.button.radius,
                        textTransform: "none",
                        padding: "6px 16px",
                        fontSize: "0.875rem",
                        fontWeight: 600,
                    },
                },
                variants: [
                    {
                        props: { variant: "contained", color: "primary" },
                        style: {
                            boxShadow: tokens.button.primaryShadow,
                            background: tokens.button.brandGradient,
                            "&:hover": {
                                boxShadow: tokens.button.primaryHoverShadow,
                                background: tokens.button.brandGradientHover,
                            },
                            ...(tokens.button.primaryDisabledColor
                                ? {
                                      "&&.Mui-disabled": {
                                          background: tokens.button.brandGradient,
                                          color: tokens.button.primaryDisabledColor,
                                          boxShadow: "none",
                                      },
                                  }
                                : {}),
                        },
                    },
                    {
                        props: { variant: "outlined", color: "primary" },
                        style: {
                            borderWidth: 2,
                        },
                    },
                ],
            },
            MuiCard: {
                styleOverrides: {
                    root: {
                        borderRadius: tokens.card.radius,
                        boxShadow: tokens.card.shadow,
                        ...(tokens.card.background ? { backgroundColor: tokens.card.background } : {}),
                        ...(tokens.card.backgroundImage ? { backgroundImage: tokens.card.backgroundImage } : {}),
                        transition: "transform 0.3s ease, box-shadow 0.3s ease",
                        ...(tokens.card.borderTopLeft
                            ? { borderLeft: tokens.card.borderTopLeft, borderTop: tokens.card.borderTopLeft }
                            : {}),
                        ...(tokens.card.border ? { border: tokens.card.border } : {}),
                        "&:hover": {
                            boxShadow: tokens.card.hoverShadow,
                            transform: "translateY(-2px)",
                        },
                    },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: {
                        backgroundColor: tokens.appBar.background,
                        ...(tokens.appBar.color ? { color: tokens.appBar.color } : {}),
                        backdropFilter: "blur(10px)",
                        boxShadow: tokens.appBar.shadow,
                    },
                },
            },
            MuiDivider: {
                styleOverrides: {
                    root: {
                        borderColor: tokens.dividerColor,
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                    },
                    elevation1: {
                        boxShadow: tokens.paperShadows[0],
                    },
                    elevation2: {
                        boxShadow: tokens.paperShadows[1],
                    },
                    elevation3: {
                        boxShadow: tokens.paperShadows[2],
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
                        background: tokens.button.brandGradient,
                        color: tokens.chipPrimaryColor,
                    },
                },
            },
            ...(tokens.gutterBottomMargin
                ? {
                      MuiTypography: {
                          styleOverrides: {
                              gutterBottom: {
                                  marginBottom: tokens.gutterBottomMargin,
                              },
                          },
                      },
                  }
                : {}),
            MuiCssBaseline: {
                styleOverrides: {
                    body: {
                        scrollbarWidth: "thin",
                        scrollbarColor: tokens.scrollbar.color,
                        "&::-webkit-scrollbar": {
                            width: "8px",
                            height: "8px",
                        },
                        "&::-webkit-scrollbar-track": {
                            background: tokens.scrollbar.track,
                        },
                        "&::-webkit-scrollbar-thumb": {
                            background: tokens.scrollbar.thumb,
                            borderRadius: "4px",
                        },
                        "&::-webkit-scrollbar-thumb:hover": {
                            background: tokens.scrollbar.thumbHover,
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
            ...extraComponents,
        },
    });
