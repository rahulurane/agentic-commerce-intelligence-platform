import { useTheme } from "../../theme/ThemeContext";
import Icon from "../ui/Icon";

/** Light/dark switch. Persists through ThemeProvider. */
export default function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      className="btn btn--ghost btn--icon"
      onClick={toggle}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
    >
      <Icon name={theme === "dark" ? "sun" : "moon"} />
    </button>
  );
}
