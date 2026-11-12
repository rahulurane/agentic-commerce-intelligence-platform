import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import OutcomeBanner from "../components/journey/OutcomeBanner";
import { deriveResult, type JourneyInput } from "../domain/journey";
import type { CheckoutResponse } from "../api/types";

function resultFor(decision: CheckoutResponse["decision"], explanation = "test explanation") {
  const input: JourneyInput = {
    phase: "complete",
    source: "run",
    loadingHistory: false,
    request: null,
    response: {
      transaction_id: "txn_abc123",
      decision,
      route: "processor_a",
      composite_score: 0.25,
      explanation,
      recommended_method: "upi",
      partial: false,
      degraded_agents: [],
      route_alternatives: ["processor_b"],
      verdicts: {},
      trace_id: "trace_1",
    },
    transaction: null,
    roundTripMs: 250,
    replayIndex: 6,
    error: null,
  };
  return deriveResult(input);
}

describe("OutcomeBanner", () => {
  it.each([
    ["APPROVE", "approve"],
    ["CHALLENGE", "challenge"],
    ["DECLINE", "decline"],
  ])("shows %s with the %s class and the word", (decision, cls) => {
    const { container } = render(
      <OutcomeBanner
        phase="complete"
        loading={false}
        result={resultFor(decision)}
        roundTripMs={250}
      />,
    );
    expect(screen.getByRole("heading", { name: decision })).toBeInTheDocument();
    expect(container.querySelector(`.outcome--${cls}`)).not.toBeNull();
  });

  it("renders route, failover, transaction id and the measured round trip", () => {
    render(
      <OutcomeBanner
        phase="complete"
        loading={false}
        result={resultFor("APPROVE")}
        roundTripMs={250}
      />,
    );
    expect(screen.getByText("processor_a")).toBeInTheDocument();
    expect(screen.getByText("processor_b")).toBeInTheDocument();
    expect(screen.getByText("txn_abc123")).toBeInTheDocument();
    expect(screen.getByText("250 ms")).toBeInTheDocument();
  });

  it("shows a busy skeleton while evaluating", () => {
    const { container } = render(
      <OutcomeBanner phase="evaluating" loading={false} result={null} roundTripMs={null} />,
    );
    expect(container.querySelector("[aria-busy='true']")).not.toBeNull();
  });

  it("renders nothing when idle", () => {
    const { container } = render(
      <OutcomeBanner phase="idle" loading={false} result={null} roundTripMs={null} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("skips the gauge on a veto", () => {
    render(
      <OutcomeBanner
        phase="complete"
        loading={false}
        result={resultFor("DECLINE", "Hard veto: policy denial.")}
        roundTripMs={250}
      />,
    );
    expect(screen.getByText("Scoring skipped")).toBeInTheDocument();
  });
});
