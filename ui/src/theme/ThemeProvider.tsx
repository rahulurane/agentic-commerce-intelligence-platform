import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { readStorage, THEME_KEY, writeStorage } from "../lib/storage";
import { ThemeContext, type Theme } from "./ThemeContext";

// Light is the default. Only an explicit stored "dark" switches it. The OS
// prefers-color-scheme setting is deliberately ignored (see ui/README.md).
function initialTheme(): Theme {
  return readStorage(THEME_KEY) === "dark" ? "dark" : "light";
}

export default function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    writeStorage(THEME_KEY, next);
  }, []);

  const toggle = useCallback(() => {
    setThemeState((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      writeStorage(THEME_KEY, next);
      return next;
    });
  }, []);

  const value = useMemo(() => ({ theme, setTheme, toggle }), [theme, setTheme, toggle]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
