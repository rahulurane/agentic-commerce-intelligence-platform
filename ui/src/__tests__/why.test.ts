import { describe, expect, it } from "vitest";
import { why, type WhyInput } from "../domain/why";
import type { AgentVerdict } from "../api/types";

const v = (agent: string, score: number | null, hint: string | null): AgentVerdict => ({
  agent,
  score,
  hint,
});

describe("why", () => {
  it("classifies a policy veto from the explanation", () => {
    const r = why({
      decision: "DECLINE",
      explanation: "Hard veto: policy denial.",
      compositeScore: 0,
    });
    expect(r.kind).toBe("policy_veto");
    expect(r.headline).toBe("Declined: policy veto");
    expect(r.drivers).toEqual(["policy"]);
  });

  it("classifies a policy veto from the policy verdict alone", () => {
    const r = why({ decision: "DECLINE", verdicts: [v("policy", 1, "DECLINE")] });
    expect(r.kind).toBe("policy_veto");
  });

  it("classifies a fraud veto and quotes the score", () => {
    const r = why({
      decision: "DECLINE",
      explanation: "Hard veto: fraud score 0.97 >= block threshold 0.85.",
      compositeScore: 1,
      verdicts: [v("fraud", 0.97, "DECLINE")],
    });
    expect(r.kind).toBe("fraud_veto");
    expect(r.body).toContain("0.970");
    expect(r.drivers).toEqual(["fraud"]);
    // The sentinel composite (1.0) is not presented as a real factor.
    expect(r.factors.some((f) => f.startsWith("Composite"))).toBe(false);
  });

  it("classifies a fraud veto from verdicts when the explanation is missing", () => {
    const r = why({ decision: "DECLINE", verdicts: [v("fraud", 0.9, "DECLINE")] });
    expect(r.kind).toBe("fraud_veto");
  });

  it("classifies other hard vetoes as generic", () => {
    const r = why({ decision: "DECLINE", explanation: "Hard veto: something else." });
    expect(r.kind).toBe("generic_veto");
  });

  it("classifies a missing verdict fallback", () => {
    const r = why({
      decision: "CHALLENGE",
      explanation:
        "Missing risk/fraud verdict; applied configured missing-verdict policy -> CHALLENGE.",
    });
    expect(r.kind).toBe("missing_verdict");
    expect(r.body).toContain("CHALLENGE");
  });

  it("classifies a merchant step-up", () => {
    const r = why({
      decision: "CHALLENGE",
      explanation: "composite 0.28 = ...; banded to APPROVE. Merchant constraint forced step-up.",
    });
    expect(r.kind).toBe("merchant_step_up");
    expect(r.drivers).toEqual(["merchant"]);
  });

  it("classifies a borderline score challenge", () => {
    const r = why({
      decision: "CHALLENGE",
      explanation: "banded to CHALLENGE.",
      compositeScore: 0.5,
    });
    expect(r.kind).toBe("score_challenge");
    expect(r.body).toContain("0.500");
  });

  it("classifies a score decline", () => {
    const r = why({ decision: "DECLINE", explanation: "banded to DECLINE.", compositeScore: 0.8 });
    expect(r.kind).toBe("score_decline");
  });

  it("classifies a low-risk approve and includes the routing note when supplied", () => {
    const r = why({
      decision: "APPROVE",
      compositeScore: 0.2,
      route: "processor_a",
      routeAlternatives: ["processor_b"],
      verdicts: [{ ...v("routing", 0.9, "APPROVE"), rationale: "A has the best success rate." }],
    });
    expect(r.kind).toBe("low_risk_approve");
    expect(r.body).toContain("processor_a");
    expect(r.body).toContain("processor_b");
    expect(r.body).toContain("Routing note: A has the best success rate.");
    expect(r.drivers).toEqual(["risk", "fraud", "routing"]);
  });

  it("is pending when there is no decision", () => {
    expect(why({ decision: null }).kind).toBe("pending");
    expect(why({ decision: "WHATEVER" }).kind).toBe("pending");
  });

  it("classifies a free-form checkout from response data only", () => {
    const input: WhyInput = {
      decision: "APPROVE",
      explanation: "composite 0.30 = 0.50*risk 0.30 + 0.50*fraud 0.30; banded to APPROVE.",
      compositeScore: 0.3,
      route: "processor_b",
      routeAlternatives: ["processor_a"],
    };
    const r = why(input);
    expect(r.kind).toBe("low_risk_approve");
    expect(r.body).toContain("processor_b");
  });

  it("works from the explanation alone, without verdicts", () => {
    const r = why({
      decision: "DECLINE",
      explanation: "Hard veto: fraud score 0.91 >= block threshold 0.85.",
    });
    expect(r.kind).toBe("fraud_veto");
    expect(r.body).toContain("0.91");
  });
});
