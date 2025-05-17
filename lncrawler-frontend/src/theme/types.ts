import { Theme } from "@mui/material";

export type ThemeId = string;

export interface ThemeFont {
  family: string;
  url?: string; // Google Fonts URL or undefined if using system fonts
}

export interface ThemeOption {
  id: ThemeId;
  name: string;
  isDark: boolean;
  getTheme: () => import("@mui/material").Theme;
  hidden?: boolean;
  password?: string;
  font?: ThemeFont; // New property for font information
}
