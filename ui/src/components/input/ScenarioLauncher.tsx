import { SCENARIOS, type Scenario } from "../../scenarios";
import ScenarioCard from "./ScenarioCard";

interface Props {
  onRun: (scenario: Scenario) => void;
  /** Name of the scenario currently running, if any. */
  runningName: string | null;
  disabled: boolean;
  lastByKey: Record<string, string>;
}

/** The five canonical demo scenarios as cards. */
export default function ScenarioLauncher({ onRun, runningName, disabled, lastByKey }: Props) {
  return (
    <section className="card" data-tour="launcher" aria-labelledby="launcher-title">
      <div className="card__head">
        <h2 id="launcher-title">Scenarios</h2>
      </div>
      <p className="muted" style={{ marginBottom: "var(--space-4)" }}>
        Each card is a ready-made story. Press Run to send it as a checkout.
      </p>
      <div className="scenario-grid">
        {SCENARIOS.map((s) => (
          <ScenarioCard
            key={s.name}
            scenario={s}
            onRun={onRun}
            running={runningName === s.name}
            disabled={disabled}
            lastDecision={lastByKey[s.name]}
          />
        ))}
      </div>
    </section>
  );
}
