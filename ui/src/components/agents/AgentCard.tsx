import type { AgentVerdict } from "../../api/types";
import { FRAUD_BLOCK } from "../../config/thresholds";
import { TOOLTIPS } from "../../content/tooltips";
import type { AgentInfo } from "../../domain/agents";
import { formatScore } from "../../lib/format";
import Icon from "../ui/Icon";
import InfoTip from "../ui/InfoTip";
import ScoreBar from "../ui/ScoreBar";
import StatusBadge from "../ui/StatusBadge";

export type AgentCardState =
  | "idle"
  | "evaluating"
  | "waiting"
  | "received"
  | "degraded"
  | "missing";

const STATE_LABEL: Record<AgentCardState, string> = {
  idle: "Standing by",
  evaluating: "Evaluating",
  waiting: "Waiting for verdict",
  received: "Verdict received",
  degraded: "Degraded",
  missing: "No verdict stored yet",
};

interface Props {
  info: AgentInfo;
  state: AgentCardState;
  verdict?: AgentVerdict;
  /** This agent is highlighted as having driven the outcome. */
  driver: boolean;
}

const KNOWN_HINTS = ["APPROVE", "CHALLENGE", "DECLINE"];

/** One agent: always a labelled general description; reported fields only when supplied. */
export default function AgentCard({ info, state, verdict, driver }: Props) {
  const hasVerdict = state === "received" || state === "degraded";
  const hint = verdict?.hint ?? null;
  const rationale = verdict?.rationale?.trim() ? verdict.rationale.trim() : null;
  const evidence = verdict?.evidence ?? [];
  const confidence = verdict?.confidence;
  const reported = hasVerdict && (rationale || evidence.length > 0 || confidence != null);

  return (
    <li
      className={`agent-card agent-card--${state}${driver ? " agent-card--driver" : ""}`}
      aria-busy={state === "evaluating" || state === "waiting"}
    >
      {driver && (
        <p className="agent-card__ribbon">
          <Icon name="bolt" size={14} /> Drove this outcome
        </p>
      )}
      <div className="agent-card__head">
        <Icon name={info.icon} size={20} className="agent-card__icon" />
        <h4 className="agent-card__name">{info.name}</h4>
        <span className={`agent-card__state agent-card__state--${state}`}>
          {state === "evaluating" || state === "waiting" ? (
            <span className="spinner" aria-hidden="true" />
          ) : null}
          {STATE_LABEL[state]}
        </span>
      </div>
      <p className="agent-card__role">{info.role}</p>
      <div className="agent-card__badges">
        {info.badges.map((b) => (
          <span
            key={b}
            className={`badge ${b.startsWith("VETO") || b.startsWith("ADVISORY") ? "badge--outline" : "tone-neutral"}`}
          >
            {b}
          </span>
        ))}
        {info.power === "advisory" && <InfoTip term="advisory agents" text={TOOLTIPS.advisory} />}
      </div>
      <p className="agent-card__desc">
        <span className="agent-card__desc-label">General description:</span> {info.looksAt}
      </p>

      {hasVerdict && (
        <div className="agent-card__verdict">
          <ScoreBar
            label={`${info.name} score`}
            value={verdict?.score ?? null}
            tick={info.key === "fraud" ? FRAUD_BLOCK : undefined}
            tickLabel={info.key === "fraud" ? `Default block threshold ${FRAUD_BLOCK}` : undefined}
          />
          <div className="agent-card__hint">
            {hint && KNOWN_HINTS.includes(hint.toUpperCase()) ? (
              <StatusBadge decision={hint} prefix="Hint" />
            ) : (
              <span className="badge tone-neutral">No hint</span>
            )}
            {state === "degraded" && (
              <span className="badge tone-warning">
                <Icon name="alert-triangle" size={14} />
                Templated explanation
                <InfoTip term="degraded" text={TOOLTIPS.degraded} />
              </span>
            )}
          </div>
          {info.key === "fraud" && (
            <p className="agent-card__tickhint">
              Marker shows the default block threshold, {FRAUD_BLOCK}.
            </p>
          )}
        </div>
      )}

      {reported && (
        <div className="agent-card__reported">
          <h5>Reported by this agent</h5>
          {rationale && <p>{rationale}</p>}
          {confidence != null && <p>Confidence {formatScore(confidence)}</p>}
          {evidence.length > 0 && (
            <ul>
              {evidence.map((e, i) => (
                <li key={`${e.signal}-${i}`}>
                  {e.signal}: {String(e.value)}
                  {e.weight != null ? ` (${e.weight})` : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {state === "missing" && (
        <p className="agent-card__missing">This agent has not reported a stored verdict.</p>
      )}
    </li>
  );
}
