import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import DecisionBanner from "../components/DecisionBanner";
import type { CheckoutResponse } from "../api/types";

function makeResponse(
  decision: CheckoutResponse["decision"],
): CheckoutResponse {
  return {
    transaction_id: "txn_abc123",
    decision,
    route: "processor_a",
    composite_score: 0.25,
    explanation: "test explanation",
    recommended_method: "upi",
    partial: false,
    degraded_agents: [],
    route_alternatives: ["processor_b"],
    verdicts: {},
    trace_id: "trace_1",
  };
}

describe("DecisionBanner", () => {
  it("shows APPROVE with the approve color class", () => {
    const { container } = render(
      <DecisionBanner decision={makeResponse("APPROVE")} />,
    );
    expect(screen.getByText("APPROVE")).toBeInTheDocument();
    expect(container.querySelector(".decision-banner.approve")).not.toBeNull();
  });

  it("shows CHALLENGE with the challenge color class", () => {
    const { container } = render(
      <DecisionBanner decision={makeResponse("CHALLENGE")} />,
    );
    expect(screen.getByText("CHALLENGE")).toBeInTheDocument();
    expect(container.querySelector(".decision-banner.challenge")).not.toBeNull();
  });

  it("shows DECLINE with the decline color class", () => {
    const { container } = render(
      <DecisionBanner decision={makeResponse("DECLINE")} />,
    );
    expect(screen.getByText("DECLINE")).toBeInTheDocument();
    expect(container.querySelector(".decision-banner.decline")).not.toBeNull();
  });

  it("renders route, alternatives and transaction id", () => {
    render(<DecisionBanner decision={makeResponse("APPROVE")} />);
    expect(screen.getByText("txn_abc123")).toBeInTheDocument();
    expect(screen.getByText("processor_a")).toBeInTheDocument();
    expect(screen.getByText("processor_b")).toBeInTheDocument();
  });
});
