import { describe, expect, it } from "vitest";
import type { CheckoutResponse, TransactionView } from "../api/types";
import { buildJourney, deriveResult, isReplaying, type JourneyInput } from "../domain/journey";

const request = {
  merchant_id: "mrc_demo",
  customer_id: "cus_clean",
  amount: 120,
  currency: "INR",
  payment_method: { type: "upi", token: "tok_x" },
  context: { device_fingerprint: "dev_clean" },
};

function response(over: Partial<CheckoutResponse> = {}): CheckoutResponse {
  return {
    transaction_id: "txn_1",
    decision: "APPROVE",
    route: "processor_a",
    composite_score: 0.2,
    explanation: "composite 0.20 = 0.50*risk 0.10 + 0.50*fraud 0.30; banded to APPROVE.",
    recommended_method: "upi",
    partial: false,
    degraded_agents: [],
    route_alternatives: ["processor_b"],
    verdicts: {},
    trace_id: "trace_1",
    ...over,
  };
}

function tx(n: number): TransactionView {
  const agents = ["risk", "fraud", "routing", "policy", "merchant", "checkout_personalization"];
  return {
    transaction_id: "txn_1",
    customer_id: "cus_clean",
    amount: 120,
    status: "APPROVED",
    decision: "APPROVE",
    composite_score: 0.2,
    strategy: "weighted_veto",
    verdicts: agents.slice(0, n).map((agent) => ({ agent, score: 0.1, hint: "APPROVE" })),
    created_at: null,
  };
}

function input(over: Partial<JourneyInput> = {}): JourneyInput {
  return {
    phase: "complete",
    source: "run",
    loadingHistory: false,
    request,
    response: response(),
    transaction: tx(6),
    roundTripMs: 123.4,
    replayIndex: 6,
    error: null,
    ...over,
  };
}

const statuses = (i: JourneyInput) => buildJourney(i).map((s) => s.status);
const text = (i: JourneyInput, stage: number) =>
  buildJourney(i)[stage].happened.concat(buildJourney(i)[stage].notes).join(" ");

describe("buildJourney", () => {
  it("always yields six stages", () => {
    expect(buildJourney(input())).toHaveLength(6);
  });

  it("is idle with no data", () => {
    const i = input({ phase: "idle", response: null, transaction: null, request: null });
    expect(statuses(i)).toEqual(Array(6).fill("idle"));
  });

  it("is indeterminate while evaluating", () => {
    const i = input({ phase: "evaluating", response: null, transaction: null });
    expect(statuses(i)).toEqual(Array(6).fill("evaluating"));
    expect(buildJourney(i).every((s) => s.happened.length === 0)).toBe(true);
  });

  it("marks stages as error when the request failed", () => {
    const i = input({ phase: "error", response: null, transaction: null, error: "x" });
    expect(statuses(i)).toEqual(Array(6).fill("error"));
  });

  it("queues stages that have not been revealed yet during replay", () => {
    const i = input({ phase: "verdicts_pending", transaction: null, replayIndex: 2 });
    expect(isReplaying(i)).toBe(true);
    expect(statuses(i).slice(2)).toEqual(Array(4).fill("queued"));
    expect(statuses(i)[0]).toBe("done");
  });

  it("checks stage 2 and 3 while verdicts are pending", () => {
    const s = statuses(input({ phase: "verdicts_pending", transaction: null }));
    expect(s[1]).toBe("checking");
    expect(s[2]).toBe("checking");
  });

  it("uses real data for a complete APPROVE", () => {
    const i = input();
    expect(text(i, 0)).toContain("Received 120.00 INR from cus_clean for mrc_demo.");
    expect(text(i, 0)).toContain("Round trip measured in your browser: 123 ms.");
    expect(text(i, 1)).toContain("6 agents produced verdicts");
    expect(text(i, 2)).toContain("6 of 6 verdicts received.");
    expect(text(i, 3)).toContain("Composite score: 0.200.");
    expect(buildJourney(i)[3].quote).toContain("banded to APPROVE");
    expect(text(i, 4)).toContain("Routed to processor_a.");
    expect(text(i, 4)).toContain("Failover order: processor_b.");
    expect(text(i, 4)).toContain("not returned by the API");
    expect(text(i, 5)).toContain("Trace trace_1");
    expect(text(i, 5)).toContain("6 agent verdicts stored");
  });

  it("describes CHALLENGE as held, not charged", () => {
    const i = input({ response: response({ decision: "CHALLENGE", composite_score: 0.5 }) });
    expect(text(i, 4)).toContain("Held for extra verification");
  });

  it("describes DECLINE with no route and skips scoring on a veto", () => {
    const i = input({
      response: response({
        decision: "DECLINE",
        route: null,
        route_alternatives: [],
        composite_score: 1,
        explanation: "Hard veto: fraud score 0.97 >= block threshold 0.85.",
      }),
    });
    expect(text(i, 4)).toContain("No route chosen and no charge attempted.");
    expect(text(i, 3)).toContain("Scoring skipped");
    expect(text(i, 3)).not.toContain("Composite score");
  });

  it("is not confirmed when no verdicts arrived", () => {
    const i = input({ phase: "partial", transaction: tx(0) });
    const s = buildJourney(i);
    expect(s[1].status).toBe("unconfirmed");
    expect(s[1].happened[0]).toContain("Not confirmed yet");
    expect(s[2].happened[0]).toBe("0 of 6 verdicts received.");
  });

  it("lists degraded agents", () => {
    const i = input({ phase: "partial", response: response({ degraded_agents: ["routing"] }) });
    expect(text(i, 2)).toContain("Degraded: routing.");
  });

  it("builds a history-selected journey from the GET only", () => {
    const i = input({
      source: "history",
      request: null,
      response: null,
      replayIndex: 0,
      roundTripMs: null,
    });
    expect(isReplaying(i)).toBe(false);
    expect(text(i, 0)).toContain("Loaded from history");
    expect(text(i, 0)).not.toContain("Round trip");
    expect(text(i, 4)).toContain("Route details are only available right after a checkout.");
    expect(statuses(i)).toEqual(Array(6).fill("done"));
  });

  it("never reports a timing other than the round trip", () => {
    const all = buildJourney(input())
      .flatMap((s) => [...s.happened, ...s.notes])
      .join(" ");
    expect(all.match(/\d+ ms/g)).toEqual(["123 ms"]);
  });
});

describe("deriveResult", () => {
  it("returns null without data", () => {
    expect(deriveResult(input({ response: null, transaction: null }))).toBeNull();
  });

  it("flags a veto", () => {
    const r = deriveResult(
      input({
        response: response({ decision: "DECLINE", explanation: "Hard veto: policy denial." }),
      }),
    );
    expect(r?.veto).toBe(true);
    expect(r?.why.kind).toBe("policy_veto");
  });
});
