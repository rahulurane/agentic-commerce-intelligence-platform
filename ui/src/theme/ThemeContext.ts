import { createContext, useContext } from "react";

export type Theme = "light" | "dark";

export interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggle: () => void;
}

// Safe default so components render (as light) even without a provider, e.g. in tests.
export const ThemeContext = createContext<ThemeContextValue>({
  theme: "light",
  setTheme: () => undefined,
  toggle: () => undefined,
});

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
