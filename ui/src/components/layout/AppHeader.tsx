import HelpButton from "../help/HelpButton";
import Icon from "../ui/Icon";
import BrandMark from "./BrandMark";
import ConnectionStatus from "./ConnectionStatus";
import ThemeToggle from "./ThemeToggle";

/** Sticky header: brand slot, title, connection pill, tour, help and theme toggle. */
interface Props {
  onTour: () => void;
  onHelp: () => void;
}

export default function AppHeader({ onTour, onHelp }: Props) {
  return (
    <header className="app-header">
      <BrandMark />
      <div className="app-header__title">
        <h1>Decision Intelligence</h1>
        <p>Every checkout, decided before the payment runs.</p>
      </div>
      <div className="app-header__actions">
        <ConnectionStatus />
        <button type="button" className="btn btn--ghost btn--sm" onClick={onTour}>
          <Icon name="play" size={16} />
          Tour
        </button>
        <HelpButton onClick={onHelp} />
        <ThemeToggle />
      </div>
    </header>
  );
}
