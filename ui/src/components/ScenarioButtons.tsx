import { SCENARIOS, type Scenario } from "../scenarios";
import { decisionColor } from "../decision";

interface Props {
  onRun: (scenario: Scenario) => void;
  disabled: boolean;
}

/** Row of one-click buttons that run each canonical demo scenario. */
export default function ScenarioButtons({ onRun, disabled }: Props) {
  return (
    <section className="scenarios">
      <h2>Demo scenarios</h2>
      <p className="muted">
        One click POSTs the scenario to <code>/v1/checkout</code> and polls for the
        six agent verdicts.
      </p>
      <div className="scenario-grid">
        {SCENARIOS.map((s) => (
          <button
            key={s.name}
            type="button"
            className={`scenario-btn ${decisionColor(s.expected)}`}
            onClick={() => onRun(s)}
            disabled={disabled}
            title={s.blurb}
          >
            <span className="scenario-label">{s.label}</span>
            <span className="scenario-meta">
              {s.customerId} · ₹{s.amount} · {s.methodType}
            </span>
            <span className="scenario-expected">expects {s.expected}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
