import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import AgentCards from "../components/AgentCards";
import type { AgentVerdict } from "../api/types";

describe("AgentCards", () => {
  it("renders a populated verdict list", () => {
    const verdicts: AgentVerdict[] = [
      { agent: "risk", score: 0.12, hint: "APPROVE" },
      { agent: "fraud", score: 0.95, hint: "DECLINE" },
      { agent: "merchant", score: 0.5, hint: "CHALLENGE" },
    ];
    render(<AgentCards verdicts={verdicts} waiting={false} />);
    expect(screen.getByText("risk")).toBeInTheDocument();
    expect(screen.getByText("fraud")).toBeInTheDocument();
    expect(screen.getByText("merchant")).toBeInTheDocument();
    expect(screen.getByText("0.120")).toBeInTheDocument();
    expect(screen.getByText("DECLINE")).toBeInTheDocument();
  });

  it("renders a waiting state for an empty verdict list without crashing", () => {
    render(<AgentCards verdicts={[]} waiting={true} />);
    expect(screen.getByText(/waiting for agents/i)).toBeInTheDocument();
    // The six-agent roster is still shown as pending placeholders.
    expect(screen.getByText("risk")).toBeInTheDocument();
    expect(screen.getByText("checkout_personalization")).toBeInTheDocument();
    expect(screen.getAllByText("pending")).toHaveLength(6);
  });

  it("renders an idle empty state when not waiting", () => {
    render(<AgentCards verdicts={[]} waiting={false} />);
    expect(screen.getByText(/no verdicts recorded/i)).toBeInTheDocument();
  });
});
