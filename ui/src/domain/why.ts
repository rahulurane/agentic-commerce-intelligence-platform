// Plain-English "why" for a decision, derived ONLY from data the API returned. The engine's
// own explanation markers are the primary signal (available even when verdicts are missing);
// verdicts corroborate. This never recomputes or changes a decision.
import type { AgentVerdict, Decision } from "../api/types";
import { APPROVE_MAX, CHALLENGE_MAX, FRAUD_BLOCK } from "../config/thresholds";
import { formatScore } from "../lib/format";
import type { AgentKey } from "./agents";

export type WhyKind =
  | "policy_veto"
  | "fraud_veto"
  | "generic_veto"
  | "missing_verdict"
  | "score_decline"
  | "merchant_step_up"
  | "score_challenge"
  | "low_risk_approve"
  | "pending";

export interface WhyInput {
  decision: Decision | null | undefined;
  explanation?: string | null;
  compositeScore?: number | null;
  route?: string | null;
  routeAlternatives?: string[];
  verdicts?: AgentVerdict[];
}

export interface WhyResult {
  kind: WhyKind;
  headline: string;
  body: string;
  drivers: AgentKey[];
  factors: string[];
}

function verdictFor(verdicts: AgentVerdict[], agent: string): AgentVerdict | undefined {
  return verdicts.find((v) => v.agent === agent);
}

function routingNote(verdicts: AgentVerdict[]): string | null {
  const rationale = verdictFor(verdicts, "routing")?.rationale;
  return rationale && rationale.trim() ? rationale.trim() : null;
}

export function why(input: WhyInput): WhyResult {
  const decision = (input.decision ?? "").toUpperCase();
  const text = (input.explanation ?? "").toLowerCase();
  const verdicts = input.verdicts ?? [];
  const alts = input.routeAlternatives ?? [];
  const composite = formatScore(input.compositeScore);
  const fraud = verdictFor(verdicts, "fraud");
  const policy = verdictFor(verdicts, "policy");
  const isVeto = text.startsWith("hard veto");

  const factors: string[] = [];
  if (!isVeto && input.compositeScore != null) {
    factors.push(`Composite score ${composite}`);
  }
  if (fraud?.score != null) {
    factors.push(`Fraud score ${formatScore(fraud.score)}`);
  }
  if (input.route) {
    factors.push(`Route ${input.route}`);
  }

  const make = (
    kind: WhyKind,
    headline: string,
    body: string,
    drivers: AgentKey[] = [],
  ): WhyResult => ({ kind, headline, body, drivers, factors });

  if (decision !== "APPROVE" && decision !== "CHALLENGE" && decision !== "DECLINE") {
    return make("pending", "Waiting for a decision", "");
  }

  if (decision === "DECLINE") {
    if (text.includes("policy denial") || policy?.hint?.toUpperCase() === "DECLINE") {
      return make(
        "policy_veto",
        "Declined: policy veto",
        "The Policy agent denied this checkout, for example because of a sanctions or compliance rule. A policy denial is final: no score can override it.",
        ["policy"],
      );
    }
    const fraudScoreInText = /fraud score ([0-9.]+)/.exec(text)?.[1];
    if (
      (isVeto && text.includes("fraud score")) ||
      (fraud?.score != null && fraud.score >= FRAUD_BLOCK)
    ) {
      const shown =
        fraud?.score != null ? formatScore(fraud.score) : (fraudScoreInText ?? "a very high value");
      return make(
        "fraud_veto",
        "Declined: fraud veto",
        `The Fraud agent scored this checkout ${shown}, at or above the default block threshold of ${FRAUD_BLOCK}. A veto ends the evaluation straight away, whatever the other agents said.`,
        ["fraud"],
      );
    }
    if (isVeto) {
      return make(
        "generic_veto",
        "Declined: hard veto",
        "A hard rule ended the evaluation. See the engine's note below.",
      );
    }
  }

  if (text.includes("missing risk/fraud verdict")) {
    return make(
      "missing_verdict",
      "Safe default applied",
      `A required Risk or Fraud verdict did not arrive in time, so the platform used its safe default (${decision}).`,
    );
  }

  if (decision === "DECLINE") {
    return make(
      "score_decline",
      "Declined: score too high",
      `The composite score ${composite} is above the challenge limit (default ${CHALLENGE_MAX.toFixed(2)}).`,
      ["risk", "fraud"],
    );
  }

  if (decision === "CHALLENGE") {
    if (text.includes("merchant constraint")) {
      return make(
        "merchant_step_up",
        "Challenge: merchant step-up",
        "The risk and fraud scores alone would have approved this. The merchant's rules ask for extra verification on this kind of purchase, so it is stepped up.",
        ["merchant"],
      );
    }
    return make(
      "score_challenge",
      "Challenge: borderline score",
      `The composite score ${composite} sits in the step-up band (above ${APPROVE_MAX}, up to ${CHALLENGE_MAX.toFixed(2)}), so extra verification is requested.`,
      ["risk", "fraud"],
    );
  }

  const routed = input.route ? ` Routed to ${input.route};` : "";
  const failover =
    alts.length > 0 ? ` ${alts.join(", ")} kept as failover.` : " No failover listed.";
  const note = routingNote(verdicts);
  return make(
    "low_risk_approve",
    "Approved: low risk",
    `No vetoes fired and the composite score ${composite} is at or below ${APPROVE_MAX}.${routed}${failover}${note ? ` Routing note: ${note}` : ""}`,
    ["risk", "fraud", "routing"],
  );
}
