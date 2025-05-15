import { ThemeOption } from "./types";
import { lightTheme } from "./lightTheme";
import { darkTheme } from "./darkTheme";
import { sepiaToneTheme } from "./sepiaTone";
import { oceanicTheme } from "./oceanic";
import { highContrastTheme } from "./highContrastTheme";

export const availableThemes: ThemeOption[] = [
    lightTheme,
    darkTheme,
    sepiaToneTheme,
    oceanicTheme,
    highContrastTheme,
];

export const getThemeById = (id: string): ThemeOption => {
    return availableThemes.find(theme => theme.id === id) || lightTheme;
};
