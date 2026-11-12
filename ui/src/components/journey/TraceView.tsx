import type { ExplainView } from "../../api/types";
import { decisionLabel } from "../../decision";
import { agentInfo } from "../../domain/agents";
import { formatScore } from "../../lib/format";
import CopyButton from "../ui/CopyButton";
import Disclosure from "../ui/Disclosure";
import StatusBadge from "../ui/StatusBadge";

interface Props {
  transactionId: string;
  explain: ExplainView | null;
  onLoad: () => void;
}

/** The stored decision trace (GET /explain): structured, with a verdict table and raw JSON. */
export default function TraceView({ transactionId, explain, onLoad }: Props) {
  return (
    <section className="card trace" aria-labelledby="trace-title">
      <div className="card__head">
        <h2 id="trace-title">Decision trace</h2>
        <CopyButton text={transactionId} what="transaction ID" />
      </div>
      {!explain ? (
        <div>
          <p className="muted">
            The full stored trace: inputs, strategy, every verdict and the final decision.
          </p>
          <button type="button" className="btn" onClick={onLoad}>
            Show decision trace
          </button>
        </div>
      ) : (
        <>
          <dl className="trace__facts">
            <div>
              <dt>Customer</dt>
              <dd>{explain.inputs.customer_id ?? "n/a"}</dd>
            </div>
            <div>
              <dt>Amount</dt>
              <dd>{explain.inputs.amount ?? "n/a"}</dd>
            </div>
            <div>
              <dt>Strategy</dt>
              <dd>{explain.strategy ?? "n/a"}</dd>
            </div>
            <div>
              <dt>Final decision</dt>
              <dd className="trace__final">
                <StatusBadge decision={explain.final_decision.decision} />
                <span>
                  {explain.final_decision.composite_score != null &&
                    `score ${formatScore(explain.final_decision.composite_score)}`}
                  {explain.final_decision.status ? ` · ${explain.final_decision.status}` : ""}
                </span>
              </dd>
            </div>
          </dl>
          {explain.verdicts.length > 0 && (
            <table className="explain-table">
              <caption className="sr-only">Agent verdicts in the stored trace</caption>
              <thead>
                <tr>
                  <th scope="col">Agent</th>
                  <th scope="col">Score</th>
                  <th scope="col">Hint</th>
                </tr>
              </thead>
              <tbody>
                {explain.verdicts.map((v) => (
                  <tr key={v.agent}>
                    <td>{agentInfo(v.agent)?.name ?? v.agent}</td>
                    <td>{formatScore(v.score)}</td>
                    <td>{v.hint ? decisionLabel(v.hint) : "n/a"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <Disclosure title="Raw JSON">
            <pre className="trace__json">{JSON.stringify(explain, null, 2)}</pre>
          </Disclosure>
        </>
      )}
    </section>
  );
}
