// Pure builder: run state -> the six Decision Journey stage models. Every "what happened"
// line comes from data the API returned (or the request we sent). The only timing is the
// measured browser round trip. Nothing here decides or re-derives a decision.
import type {
  AgentVerdict,
  CheckoutRequest,
  CheckoutResponse,
  Decision,
  TransactionView,
} from "../api/types";
import { STAGE_CONTENT, type StageContent } from "../content/stages";
import { decisionLabel } from "../decision";
import { formatAmount, formatMs, formatScore, humanize } from "../lib/format";
import { AGENT_KEYS } from "./agents";
import { isVetoKind, why, type WhyResult } from "./why";

export type StageStatus =
  | "idle"
  | "evaluating"
  | "queued"
  | "checking"
  | "done"
  | "unconfirmed"
  | "error";

export const STAGE_STATUS_LABEL: Record<StageStatus, string> = {
  idle: "Standing by",
  evaluating: "Evaluating",
  queued: "Waiting",
  checking: "Checking",
  done: "Done",
  unconfirmed: "Not confirmed",
  error: "Error",
};

export interface StageModel {
  content: StageContent;
  status: StageStatus;
  /** "What happened" lines, built from real data only. */
  happened: string[];
  /** The engine's own words (stage 4), shown in a quote block. */
  quote: string | null;
  /** Fixed honesty notes (what the API does not return). */
  notes: string[];
}

/** The slice of run state the journey needs (RunState satisfies it structurally). */
export interface JourneyInput {
  phase: "idle" | "evaluating" | "verdicts_pending" | "complete" | "partial" | "error";
  source: "run" | "history";
  loadingHistory: boolean;
  request: CheckoutRequest | null;
  response: CheckoutResponse | null;
  transaction: TransactionView | null;
  roundTripMs: number | null;
  replayIndex: number;
  error: string | null;
}

/** Normalised result, from the POST response when present, else the stored transaction. */
export interface RunResult {
  transactionId: string;
  traceId: string | null;
  decision: Decision | null;
  compositeScore: number | null;
  explanation: string | null;
  route: string | null;
  routeAlternatives: string[];
  recommendedMethod: string | null;
  partial: boolean;
  degradedAgents: string[];
  status: string | null;
  strategy: string | null;
  verdicts: AgentVerdict[];
  why: WhyResult;
  /** A hard veto ended the evaluation, so composite_score is a sentinel, not a real score. */
  veto: boolean;
}

export const STAGE_COUNT = STAGE_CONTENT.length;
/** Delay between stages during the labelled replay. */
export const REPLAY_STEP_MS = 450;

export function deriveResult(input: JourneyInput): RunResult | null {
  const { response, transaction } = input;
  if (!response && !transaction) {
    return null;
  }
  const verdicts = transaction?.verdicts ?? [];
  const decision = response?.decision ?? transaction?.decision ?? null;
  const compositeScore = response?.composite_score ?? transaction?.composite_score ?? null;
  const explanation = response?.explanation ?? null;
  const route = response?.route ?? null;
  const routeAlternatives = response?.route_alternatives ?? [];
  const whyResult = why({
    decision,
    explanation,
    compositeScore,
    route,
    routeAlternatives,
    verdicts,
  });
  const degraded = new Set<string>(response?.degraded_agents ?? []);
  for (const v of verdicts) {
    if (v.degraded) {
      degraded.add(v.agent);
    }
  }
  return {
    transactionId: response?.transaction_id ?? transaction?.transaction_id ?? "",
    traceId: response?.trace_id ?? null,
    decision,
    compositeScore,
    explanation,
    route,
    routeAlternatives,
    recommendedMethod: response?.recommended_method ?? null,
    partial: response?.partial ?? false,
    degradedAgents: [...degraded],
    status: transaction?.status ?? null,
    strategy: transaction?.strategy ?? null,
    verdicts,
    why: whyResult,
    veto: isVetoKind(whyResult.kind),
  };
}

/** True while the labelled replay of a fresh result is still revealing stages. */
export function isReplaying(input: JourneyInput): boolean {
  return input.source === "run" && input.response != null && input.replayIndex < STAGE_COUNT;
}

function stage1(input: JourneyInput, result: RunResult): string[] {
  const { request, roundTripMs } = input;
  const lines: string[] = [];
  if (request) {
    lines.push(
      `Received ${formatAmount(request.amount, request.currency)} from ${request.customer_id} for ${request.merchant_id}.`,
    );
  } else {
    const tx = input.transaction;
    lines.push(
      `Loaded from history: customer ${tx?.customer_id ?? "n/a"}, amount ${formatAmount(tx?.amount)}.`,
    );
  }
  lines.push(`Transaction ${result.transactionId}.`);
  if (input.source === "run" && roundTripMs != null) {
    lines.push(`Round trip measured in your browser: ${formatMs(roundTripMs)}.`);
  }
  return lines;
}

function stage3(result: RunResult): string[] {
  const received = result.verdicts.length;
  const lines = [`${received} of ${AGENT_KEYS.length} verdicts received.`];
  if (result.degradedAgents.length > 0) {
    lines.push(
      `Degraded: ${result.degradedAgents.map(humanize).join(", ")}. Their scores are valid; only the written explanation fell back to a template.`,
    );
  }
  return lines;
}

function stage4(result: RunResult): string[] {
  const lines = [`Decision: ${decisionLabel(result.decision)}.`];
  lines.push(
    result.veto
      ? "Scoring skipped: a veto ended the evaluation."
      : `Composite score: ${formatScore(result.compositeScore)}.`,
  );
  if (result.strategy) {
    lines.push(`Strategy: ${result.strategy}.`);
  }
  return lines;
}

function stage5(input: JourneyInput, result: RunResult): { lines: string[]; notes: string[] } {
  const notes: string[] = [];
  const decision = (result.decision ?? "").toUpperCase();
  const lines: string[] = [];
  if (input.source === "history") {
    lines.push("Route details are only available right after a checkout.");
  } else if (decision === "APPROVE") {
    lines.push(
      result.route ? `Routed to ${result.route}.` : "No route was reported.",
      `Failover order: ${result.routeAlternatives.length > 0 ? result.routeAlternatives.join(", ") : "none"}.`,
    );
    if (result.recommendedMethod) {
      lines.push(`Suggested payment method: ${result.recommendedMethod}.`);
    }
    if (result.status) {
      lines.push(`Status: ${result.status}.`);
    }
  } else if (decision === "CHALLENGE") {
    lines.push(
      `Held for extra verification. Route ${result.route ?? "n/a"} is reserved; no charge is attempted until the customer steps up.`,
    );
  } else if (decision === "DECLINE") {
    lines.push("No route chosen and no charge attempted.");
  } else {
    lines.push("Waiting for a decision.");
  }
  notes.push("The simulated charge result is not returned by the API.");
  return { lines, notes };
}

function stage6(result: RunResult): string[] {
  const parts = [`Transaction ${result.transactionId}`];
  if (result.traceId) {
    parts.push(`Trace ${result.traceId}`);
  }
  if (result.status) {
    parts.push(`Status ${result.status}`);
  }
  parts.push(`${result.verdicts.length} agent verdicts stored`);
  return [`${parts.join(" · ")}.`];
}

export function buildJourney(input: JourneyInput): StageModel[] {
  const evaluating = input.phase === "evaluating" || input.loadingHistory;
  const result = deriveResult(input);
  const replaying = isReplaying(input);

  return STAGE_CONTENT.map((content, i): StageModel => {
    const base = { content, happened: [] as string[], quote: null, notes: [] as string[] };

    if (input.phase === "error" && !result) {
      return {
        ...base,
        status: "error",
        happened: i === 0 ? ["The request did not complete, so there is no result to show."] : [],
      };
    }
    if (evaluating) {
      return { ...base, status: "evaluating" };
    }
    if (!result) {
      return { ...base, status: "idle" };
    }
    if (replaying && i >= input.replayIndex) {
      return { ...base, status: "queued" };
    }

    const pending = input.phase === "verdicts_pending";
    const n = result.verdicts.length;
    switch (i) {
      case 0:
        return { ...base, status: "done", happened: stage1(input, result) };
      case 1: {
        const notes = [
          "The API does not return the representation itself, so its feature values are not shown here.",
        ];
        if (pending) {
          return { ...base, status: "checking", happened: ["Checking for agent verdicts."], notes };
        }
        if (n === 0) {
          return {
            ...base,
            status: "unconfirmed",
            happened: ["Not confirmed yet: no agent verdicts have arrived."],
            notes,
          };
        }
        const who = n === 1 ? "1 agent produced a verdict" : `${n} agents produced verdicts`;
        return {
          ...base,
          status: "done",
          happened: [`${who} from it, which confirms it was built.`],
          notes,
        };
      }
      case 2:
        return {
          ...base,
          status: pending ? "checking" : "done",
          happened: stage3(result),
        };
      case 3:
        return {
          ...base,
          status: "done",
          happened: stage4(result),
          quote: result.explanation ? result.explanation : null,
        };
      case 4: {
        const s5 = stage5(input, result);
        return { ...base, status: "done", happened: s5.lines, notes: s5.notes };
      }
      default:
        return { ...base, status: "done", happened: stage6(result) };
    }
  });
}
