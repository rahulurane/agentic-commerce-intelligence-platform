import type { CheckoutResponse } from "../api/types";
import { decisionColor, decisionLabel } from "../decision";

interface Props {
  decision: CheckoutResponse;
}

/** Prominent colored banner summarizing the decision returned by POST /v1/checkout. */
export default function DecisionBanner({ decision }: Props) {
  const color = decisionColor(decision.decision);
  return (
    <section className={`decision-banner ${color}`}>
      <div className="decision-headline">
        <span className="decision-word">{decisionLabel(decision.decision)}</span>
        {decision.composite_score != null && (
          <span className="decision-score">
            score {decision.composite_score.toFixed(3)}
          </span>
        )}
      </div>
      <dl className="decision-details">
        <div>
          <dt>Transaction</dt>
          <dd>
            <code>{decision.transaction_id}</code>
          </dd>
        </div>
        <div>
          <dt>Route</dt>
          <dd>{decision.route ?? "—"}</dd>
        </div>
        {decision.route_alternatives.length > 0 && (
          <div>
            <dt>Alternatives</dt>
            <dd>{decision.route_alternatives.join(", ")}</dd>
          </div>
        )}
        <div>
          <dt>Recommended method</dt>
          <dd>{decision.recommended_method ?? "—"}</dd>
        </div>
        {decision.degraded_agents.length > 0 && (
          <div>
            <dt>Degraded agents</dt>
            <dd>{decision.degraded_agents.join(", ")}</dd>
          </div>
        )}
      </dl>
      {decision.explanation && (
        <p className="decision-explanation">{decision.explanation}</p>
      )}
      {decision.partial && (
        <p className="muted">
          Decision returned before all agents committed (partial) — verdicts shown
          below are polled from the transaction record.
        </p>
      )}
    </section>
  );
}
