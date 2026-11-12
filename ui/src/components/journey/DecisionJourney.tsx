import { useEffect, useMemo, useState } from "react";
import {
  REPLAY_STEP_MS,
  STAGE_COUNT,
  buildJourney,
  isReplaying,
  type RunResult,
} from "../../domain/journey";
import { useReducedMotion } from "../../lib/useReducedMotion";
import type { RunState } from "../../state/useCheckoutRun";
import AgentCards from "../agents/AgentCards";
import CopyButton from "../ui/CopyButton";
import Icon from "../ui/Icon";
import JourneyStage from "./JourneyStage";
import ReplayNotice from "./ReplayNotice";

const JAEGER_URL = import.meta.env.VITE_JAEGER_URL ?? "http://localhost:16686";

interface Props {
  state: RunState;
  result: RunResult | null;
  onReplayIndex: (index: number) => void;
  onRetryFetch: () => void;
}

type Mode = "idle" | "evaluating" | "error" | "replay" | "settled";

function openFor(mode: Mode, replayIndex: number): Record<number, boolean> {
  switch (mode) {
    case "idle":
    case "evaluating":
      return { 2: true };
    case "replay":
      return replayIndex > 0 ? { [replayIndex - 1]: true } : {};
    case "settled":
      return { 2: true, 3: true };
    default:
      return {};
  }
}

/** The six-stage Decision Journey: honest evaluating state, labelled replay, real data. */
export default function DecisionJourney({ state, result, onReplayIndex, onRetryFetch }: Props) {
  const reduced = useReducedMotion();
  const stages = useMemo(() => buildJourney(state), [state]);
  const replaying = isReplaying(state);
  const evaluating = state.phase === "evaluating" || state.loadingHistory;

  let mode: Mode = "settled";
  if (state.phase === "error" && !result) mode = "error";
  else if (evaluating) mode = "evaluating";
  else if (!result) mode = "idle";
  else if (replaying) mode = "replay";

  const replayIndex = state.replayIndex;
  const [open, setOpen] = useState<Record<number, boolean>>(() => openFor(mode, replayIndex));
  const [dismissedFor, setDismissedFor] = useState<string | null>(null);

  // Replay: reveal one stage at a time (instantly under reduced motion).
  useEffect(() => {
    if (!replaying) {
      return;
    }
    if (reduced) {
      onReplayIndex(STAGE_COUNT);
      return;
    }
    const t = setTimeout(
      () => onReplayIndex(replayIndex + 1),
      replayIndex === 0 ? 0 : REPLAY_STEP_MS,
    );
    return () => clearTimeout(t);
  }, [replaying, reduced, replayIndex, onReplayIndex]);

  // Which stages are open follows the mode; the user can still toggle any of them.
  const openKey = mode === "replay" ? replayIndex : -1;
  useEffect(() => {
    setOpen(openFor(mode, openKey));
  }, [mode, openKey]);

  const expandable = stages.map((s) => s.status !== "queued");
  const allOpen = stages.every((_, i) => !expandable[i] || open[i]);

  function toggleAll() {
    const next: Record<number, boolean> = {};
    stages.forEach((_, i) => {
      next[i] = !allOpen;
    });
    setOpen(next);
  }

  const verdictCount = result?.verdicts.length ?? 0;
  const showReplayNotice =
    state.source === "run" && result != null && dismissedFor !== result.transactionId;
  const showPartial =
    result != null &&
    !replaying &&
    (state.phase === "partial" ||
      result.partial ||
      (verdictCount < 6 && state.phase !== "verdicts_pending"));

  return (
    <section className="card journey" aria-labelledby="journey-title" data-tour="journey">
      <div className="card__head">
        <h2 id="journey-title">Decision journey</h2>
        <button type="button" className="btn btn--sm btn--ghost" onClick={toggleAll}>
          {allOpen ? "Collapse all" : "Expand all"}
        </button>
      </div>

      {state.source === "history" && result && (
        <div className="notice notice--info" role="note">
          <Icon name="info" size={16} />
          <p>
            Loaded from history. Route and timing details are only available right after a checkout.
          </p>
        </div>
      )}
      {showReplayNotice && (
        <ReplayNotice
          replaying={replaying}
          onShowAll={() => onReplayIndex(STAGE_COUNT)}
          onDismiss={() => setDismissedFor(result.transactionId)}
        />
      )}
      {showPartial && (
        <div className="notice notice--warning" role="status">
          <Icon name="alert-triangle" size={16} />
          <p>Some agents did not report in time. The engine used its safe defaults.</p>
          {verdictCount === 0 && state.source === "run" && (
            <button type="button" className="btn btn--sm" onClick={onRetryFetch}>
              Retry fetch
            </button>
          )}
        </div>
      )}

      <ol className="journey__list">
        {stages.map((model, i) => (
          <JourneyStage
            key={model.content.id}
            model={model}
            open={Boolean(open[i])}
            onToggle={() => setOpen((o) => ({ ...o, [i]: !o[i] }))}
          >
            {i === 2 && (
              <div className="stage__agents" data-tour="agents">
                <AgentCards
                  verdicts={result?.verdicts ?? []}
                  phase={state.loadingHistory ? "evaluating" : state.phase}
                  degradedAgents={result?.degradedAgents}
                  drivers={result?.why.drivers}
                />
              </div>
            )}
            {i === 5 && result && model.status === "done" && (
              <div className="stage__links">
                <span className="stage__link-item">
                  Transaction ID
                  <CopyButton text={result.transactionId} what="transaction ID" />
                </span>
                {result.traceId && (
                  <span className="stage__link-item">
                    Trace ID
                    <CopyButton text={result.traceId} what="trace ID" />
                  </span>
                )}
                <a className="stage__link" href={JAEGER_URL} target="_blank" rel="noreferrer">
                  <Icon name="link" size={14} /> Open Jaeger
                </a>
                <p className="stage__note">In Jaeger, search service checkout-api.</p>
              </div>
            )}
          </JourneyStage>
        ))}
      </ol>
    </section>
  );
}
