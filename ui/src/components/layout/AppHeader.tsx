import BrandMark from "./BrandMark";
import ConnectionStatus from "./ConnectionStatus";
import ThemeToggle from "./ThemeToggle";

/** Sticky header: brand slot, title, connection pill and theme toggle. */
export default function AppHeader() {
  return (
    <header className="app-header">
      <BrandMark />
      <div className="app-header__title">
        <h1>Decision Intelligence</h1>
        <p>Every checkout, decided before the payment runs.</p>
      </div>
      <div className="app-header__actions">
        <ConnectionStatus />
        <ThemeToggle />
      </div>
    </header>
  );
}
