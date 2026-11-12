import Icon from "../ui/Icon";

interface Props {
  replaying: boolean;
  onShowAll: () => void;
  onDismiss: () => void;
}

/** Labels the step-by-step reveal as a replay of the real result, not live timing. */
export default function ReplayNotice({ replaying, onShowAll, onDismiss }: Props) {
  return (
    <div className="notice notice--info" role="note">
      <Icon name="play" size={16} />
      <p>
        <strong>Replay.</strong> The steps light up one after another to walk you through the real
        result. This is a replay, not live timing. The only time measured is the round trip.
      </p>
      {replaying ? (
        <button type="button" className="btn btn--sm" onClick={onShowAll}>
          Show all now
        </button>
      ) : (
        <button type="button" className="btn btn--sm btn--ghost" onClick={onDismiss}>
          Dismiss
        </button>
      )}
    </div>
  );
}
