import { Theme } from "@mui/material";

export interface ThemeOption {
  id: string;
  name: string;
  isDark: boolean;
  getTheme: () => Theme;
}

export type ThemeId = string;
