import type { ExplainView as ExplainViewData } from "../api/types";
import { decisionColor, decisionLabel } from "../decision";

interface Props {
  explain: ExplainViewData;
}

/** Renders the /explain decision trace: inputs, strategy, verdicts, final decision. */
export default function ExplainView({ explain }: Props) {
  const color = decisionColor(explain.final_decision.decision);
  return (
    <section className="explain">
      <h2>Decision trace (explain)</h2>
      <dl className="explain-inputs">
        <div>
          <dt>Customer</dt>
          <dd>{explain.inputs.customer_id ?? "—"}</dd>
        </div>
        <div>
          <dt>Amount</dt>
          <dd>{explain.inputs.amount ?? "—"}</dd>
        </div>
        <div>
          <dt>Strategy</dt>
          <dd>{explain.strategy ?? "—"}</dd>
        </div>
        <div>
          <dt>Final</dt>
          <dd className={`explain-final ${color}`}>
            {decisionLabel(explain.final_decision.decision)}
            {explain.final_decision.composite_score != null &&
              ` (${explain.final_decision.composite_score.toFixed(3)})`}
          </dd>
        </div>
      </dl>
      {explain.verdicts.length > 0 && (
        <table className="explain-table">
          <thead>
            <tr>
              <th>Agent</th>
              <th>Score</th>
              <th>Hint</th>
            </tr>
          </thead>
          <tbody>
            {explain.verdicts.map((v) => (
              <tr key={v.agent}>
                <td>{v.agent}</td>
                <td>{v.score != null ? v.score.toFixed(3) : "—"}</td>
                <td>{v.hint ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
