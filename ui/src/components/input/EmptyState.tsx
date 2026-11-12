interface Props {
  /** When provided, the tour sentence and button are shown. */
  onStartTour?: () => void;
  /** When provided, the help button is shown. */
  onOpenHelp?: () => void;
}

/** Idle-state call to action. */
export default function EmptyState({ onStartTour, onOpenHelp }: Props) {
  return (
    <section className="card empty-state">
      <h2>Start here</h2>
      <p>
        Pick a scenario on the left and press Run. In about a second you will see the decision, why
        it was made, and what each of the six agents said.
        {onStartTour ? " New here? Take the 60-second tour." : ""}
      </p>
      {(onStartTour || onOpenHelp) && (
        <div className="empty-state__actions">
          {onStartTour && (
            <button type="button" className="btn btn--primary" onClick={onStartTour}>
              Start tour
            </button>
          )}
          {onOpenHelp && (
            <button type="button" className="btn" onClick={onOpenHelp}>
              Open help guide
            </button>
          )}
        </div>
      )}
    </section>
  );
}
