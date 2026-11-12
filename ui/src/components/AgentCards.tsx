import type { AgentVerdict } from "../api/types";

interface Props {
  verdicts: AgentVerdict[];
  waiting: boolean;
}

// The six agents ACIP runs. When the polled verdicts are empty/partial we still show
// the roster so the room sees which specialists participate.
const AGENT_ROSTER = ["risk", "fraud", "routing", "policy", "merchant", "checkout_personalization"];

function hintClass(hint: string | null): string {
  switch ((hint ?? "").toUpperCase()) {
    case "APPROVE":
      return "approve";
    case "CHALLENGE":
      return "challenge";
    case "DECLINE":
      return "decline";
    default:
      return "unknown";
  }
}

/** Grid of the six agent verdict cards; tolerates an empty/partial verdict list. */
export default function AgentCards({ verdicts, waiting }: Props) {
  if (!verdicts || verdicts.length === 0) {
    return (
      <section className="agent-cards">
        <h2>Agent verdicts</h2>
        <p className="muted" role="status">
          {waiting
            ? "Waiting for agents to commit their verdicts…"
            : "No verdicts recorded yet for this transaction."}
        </p>
        <div className="agent-grid">
          {AGENT_ROSTER.map((agent) => (
            <div key={agent} className="agent-card unknown pending">
              <span className="agent-name">{agent}</span>
              <span className="agent-hint">pending</span>
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="agent-cards">
      <h2>Agent verdicts</h2>
      <div className="agent-grid">
        {verdicts.map((v) => (
          <div key={v.agent} className={`agent-card ${hintClass(v.hint)}`}>
            <span className="agent-name">{v.agent}</span>
            <span className="agent-score">{v.score != null ? v.score.toFixed(3) : "—"}</span>
            <span className="agent-hint">{v.hint ?? "—"}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
