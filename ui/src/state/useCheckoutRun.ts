// One reducer hook that owns the whole checkout run: request, response, polled verdicts,
// the real browser round trip, and the phase (plan section 6). Components are pure
// functions of this state.
import { useCallback, useReducer, useRef } from "react";
import type { CheckoutRequest, CheckoutResponse, ExplainView, TransactionView } from "../api/types";
import { ApiError, getExplain, getTransaction, pollTransaction, postCheckout } from "../api/client";
import type { RecentEntry } from "../components/input/RecentTransactions";
import { AGENT_KEYS } from "../domain/agents";

export type RunPhase =
  | "idle"
  | "evaluating"
  | "verdicts_pending"
  | "complete"
  | "partial"
  | "error";

export interface RunState {
  phase: RunPhase;
  /** "run" for a fresh checkout, "history" when a recent transaction was selected. */
  source: "run" | "history";
  request: CheckoutRequest | null;
  response: CheckoutResponse | null;
  transaction: TransactionView | null;
  explain: ExplainView | null;
  /** Real client round trip around the POST, in ms. The only timing the UI shows. */
  roundTripMs: number | null;
  /** Index of the next journey stage to reveal during replay. */
  replayIndex: number;
  error: string | null;
  /** History selection returned 404. */
  notFound: boolean;
  /** True while a history GET is in flight. */
  loadingHistory: boolean;
  activeId: string | null;
  runningKey: string | null;
  recent: RecentEntry[];
  /** Last decision per scenario key, for the "done" state on scenario cards. */
  lastByKey: Record<string, string>;
}

export const initialRunState: RunState = {
  phase: "idle",
  source: "run",
  request: null,
  response: null,
  transaction: null,
  explain: null,
  roundTripMs: null,
  replayIndex: 0,
  error: null,
  notFound: false,
  loadingHistory: false,
  activeId: null,
  runningKey: null,
  recent: [],
  lastByKey: {},
};

export type RunAction =
  | { type: "start"; request: CheckoutRequest; key: string | null }
  | { type: "posted"; response: CheckoutResponse; roundTripMs: number; label: string }
  | { type: "polled"; transaction: TransactionView | null }
  | { type: "failed"; message: string }
  | { type: "select_start"; id: string }
  | { type: "select_done"; transaction: TransactionView }
  | { type: "select_not_found" }
  | { type: "select_failed"; message: string }
  | { type: "explain"; explain: ExplainView | null }
  | { type: "replay"; index: number };

/** Complete = all six verdicts and nothing flagged partial/degraded; otherwise partial. */
function settledPhase(response: CheckoutResponse, transaction: TransactionView | null): RunPhase {
  const n = transaction?.verdicts.length ?? 0;
  const full = n >= AGENT_KEYS.length;
  return full && !response.partial && response.degraded_agents.length === 0
    ? "complete"
    : "partial";
}

export function runReducer(state: RunState, action: RunAction): RunState {
  switch (action.type) {
    case "start":
      return {
        ...state,
        phase: "evaluating",
        source: "run",
        request: action.request,
        response: null,
        transaction: null,
        explain: null,
        roundTripMs: null,
        replayIndex: 0,
        error: null,
        notFound: false,
        loadingHistory: false,
        runningKey: action.key,
      };
    case "posted": {
      const { response } = action;
      const lastByKey =
        state.runningKey && response.decision
          ? { ...state.lastByKey, [state.runningKey]: response.decision }
          : state.lastByKey;
      return {
        ...state,
        phase: "verdicts_pending",
        response,
        roundTripMs: action.roundTripMs,
        activeId: response.transaction_id,
        recent: [
          {
            transactionId: response.transaction_id,
            decision: response.decision,
            label: action.label,
          },
          ...state.recent.filter((e) => e.transactionId !== response.transaction_id),
        ],
        lastByKey,
      };
    }
    case "polled":
      return {
        ...state,
        phase: state.response ? settledPhase(state.response, action.transaction) : "partial",
        transaction: action.transaction,
        runningKey: null,
      };
    case "failed":
      return { ...state, phase: "error", error: action.message, runningKey: null };
    case "select_start":
      return {
        ...state,
        activeId: action.id,
        source: "history",
        loadingHistory: true,
        notFound: false,
        error: null,
        explain: null,
        request: null,
        response: null,
        transaction: null,
        roundTripMs: null,
      };
    case "select_done":
      return {
        ...state,
        loadingHistory: false,
        transaction: action.transaction,
        phase: action.transaction.verdicts.length >= AGENT_KEYS.length ? "complete" : "partial",
      };
    case "select_not_found":
      return { ...state, loadingHistory: false, notFound: true, phase: "idle" };
    case "select_failed":
      return { ...state, loadingHistory: false, phase: "error", error: action.message };
    case "explain":
      return { ...state, explain: action.explain };
    case "replay":
      return { ...state, replayIndex: action.index };
    default:
      return state;
  }
}

export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    return `HTTP ${err.status}. Is the checkout-api running and reachable?`;
  }
  if (err instanceof Error) {
    return `${err.message}. Is the checkout-api running and reachable?`;
  }
  return "Unknown error.";
}

export function useCheckoutRun() {
  const [state, dispatch] = useReducer(runReducer, initialRunState);
  // Guards against a slow earlier run overwriting a newer one.
  const runId = useRef(0);

  const runCheckout = useCallback(
    async (request: CheckoutRequest, label: string, key: string | null = null) => {
      const id = (runId.current += 1);
      dispatch({ type: "start", request, key });
      try {
        const t0 = performance.now();
        const response = await postCheckout(request);
        const roundTripMs = performance.now() - t0;
        if (id !== runId.current) return;
        dispatch({ type: "posted", response, roundTripMs, label });
        const transaction = await pollTransaction(response.transaction_id);
        if (id !== runId.current) return;
        dispatch({ type: "polled", transaction });
      } catch (err) {
        if (id !== runId.current) return;
        dispatch({ type: "failed", message: describeError(err) });
      }
    },
    [],
  );

  const selectRecent = useCallback(async (transactionId: string) => {
    const id = (runId.current += 1);
    dispatch({ type: "select_start", id: transactionId });
    try {
      const transaction = await getTransaction(transactionId);
      if (id !== runId.current) return;
      dispatch({ type: "select_done", transaction });
    } catch (err) {
      if (id !== runId.current) return;
      if (err instanceof ApiError && err.status === 404) {
        dispatch({ type: "select_not_found" });
      } else {
        dispatch({ type: "select_failed", message: describeError(err) });
      }
    }
  }, []);

  const loadExplain = useCallback(async (transactionId: string) => {
    try {
      dispatch({ type: "explain", explain: await getExplain(transactionId) });
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        dispatch({ type: "explain", explain: null });
      } else {
        dispatch({ type: "failed", message: describeError(err) });
      }
    }
  }, []);

  const setReplayIndex = useCallback((index: number) => dispatch({ type: "replay", index }), []);

  return { state, runCheckout, selectRecent, loadExplain, setReplayIndex };
}
