import type { AgentVerdict } from "../../api/types";
import { AGENTS, type AgentKey } from "../../domain/agents";
import type { RunPhase } from "../../state/useCheckoutRun";
import AgentCard, { type AgentCardState } from "./AgentCard";

interface Props {
  verdicts: AgentVerdict[];
  phase: RunPhase;
  /** A history GET is in flight. */
  loading?: boolean;
  degradedAgents?: string[];
  /** Agents highlighted as having driven the outcome (from why()). */
  drivers?: AgentKey[];
}

function cardState(
  phase: RunPhase,
  loading: boolean,
  verdict: AgentVerdict | undefined,
  degradedAgents: string[],
  key: string,
): AgentCardState {
  if (loading || phase === "evaluating") {
    return "evaluating";
  }
  if (verdict) {
    return verdict.degraded || degradedAgents.includes(key) ? "degraded" : "received";
  }
  switch (phase) {
    case "verdicts_pending":
      return "waiting";
    case "complete":
    case "partial":
      return "missing";
    default:
      return "idle";
  }
}

/** The six agent cards. Tolerates empty or partial verdict lists. */
export default function AgentCards({
  verdicts,
  phase,
  loading = false,
  degradedAgents = [],
  drivers = [],
}: Props) {
  return (
    <ul className="agent-grid" aria-label="Agent verdicts">
      {AGENTS.map((info) => {
        const verdict = verdicts.find((v) => v.agent === info.key);
        const state = cardState(phase, loading, verdict, degradedAgents, info.key);
        return (
          <AgentCard
            key={info.key}
            info={info}
            verdict={verdict}
            state={state}
            driver={
              drivers.includes(info.key) && !["idle", "evaluating", "waiting"].includes(state)
            }
          />
        );
      })}
    </ul>
  );
}
