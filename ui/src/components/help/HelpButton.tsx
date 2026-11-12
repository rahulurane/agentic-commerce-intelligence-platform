import Icon from "../ui/Icon";

interface Props {
  onClick: () => void;
}

/** Header Help button with a visible "?" keyboard hint. */
export default function HelpButton({ onClick }: Props) {
  return (
    <button
      type="button"
      className="btn btn--ghost btn--sm help-button"
      onClick={onClick}
      aria-haspopup="dialog"
      aria-keyshortcuts="?"
      data-tour="help"
    >
      <Icon name="help" size={18} />
      Help
      <kbd className="help-button__key" aria-hidden="true">
        ?
      </kbd>
    </button>
  );
}
