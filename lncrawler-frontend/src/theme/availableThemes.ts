import { ThemeOption } from "./types";
import { lightTheme } from "./themes/lightTheme";
import { darkTheme } from "./themes/darkTheme";
import { sepiaToneTheme } from "./themes/sepiaTone";
import { oceanicTheme } from "./themes/oceanic";
import { highContrastTheme } from "./themes/highContrastTheme";
import { pinkTheme } from "./themes/pink";
import { hackerTheme } from "./themes/hackerTheme";
import { tfTheme } from "./themes/tfTheme";
import { windows98Theme } from "./themes/windows98Theme";
import { catTheme } from "./themes/catTheme";
import { rainbowTheme } from "./themes/rainbowTheme";
import { horrorTheme } from "./themes/horrorTheme";
import { galaxyTheme } from "./themes/galaxyTheme";

export const availableThemes: ThemeOption[] = [
    lightTheme,
    darkTheme,
    sepiaToneTheme,
    oceanicTheme,
    highContrastTheme,
    pinkTheme,
    hackerTheme,
    tfTheme,
    windows98Theme,
    catTheme,
    rainbowTheme,
    horrorTheme,
    galaxyTheme,
];

export const getThemeById = (id: string): ThemeOption => {
    return availableThemes.find(theme => theme.id === id) || lightTheme;
};
