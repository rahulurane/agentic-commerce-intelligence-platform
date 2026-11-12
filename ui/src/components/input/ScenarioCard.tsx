import type { Scenario } from "../../scenarios";
import Icon from "../ui/Icon";
import StatusBadge from "../ui/StatusBadge";

interface Props {
  scenario: Scenario;
  onRun: (scenario: Scenario) => void;
  running: boolean;
  /** Another run is in flight, so every card is disabled. */
  disabled: boolean;
  /** The decision returned the last time this scenario ran in this session. */
  lastDecision?: string;
}

/** One ready-made story: ready (Run), running (spinner), or done (last decision chip). */
export default function ScenarioCard({ scenario, onRun, running, disabled, lastDecision }: Props) {
  return (
    <article className="scenario-card" aria-busy={running}>
      <div className="scenario-card__head">
        <Icon name={scenario.icon} />
        <h3>{scenario.label}</h3>
      </div>
      <p className="scenario-card__story">{scenario.story}</p>
      <p className="muted">{scenario.demonstrates}</p>
      <div className="scenario-card__meta">
        <StatusBadge decision={scenario.expected} prefix="Expected" />
        <span>
          {scenario.customerId} · {scenario.amount} · {scenario.methodType}
        </span>
      </div>
      <div className="scenario-card__actions">
        <button
          type="button"
          className="btn btn--primary btn--sm"
          onClick={() => onRun(scenario)}
          disabled={disabled || running}
          aria-label={`Run ${scenario.label}`}
        >
          {running ? (
            <span className="spinner" aria-hidden="true" />
          ) : (
            <Icon name="play" size={16} />
          )}
          {running ? "Running" : "Run"}
        </button>
        {lastDecision && !running && (
          <span>
            <span className="sr-only">Last result: </span>
            <StatusBadge decision={lastDecision} />
          </span>
        )}
      </div>
    </article>
  );
}
