import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import AgentCards from "../components/agents/AgentCards";
import type { AgentVerdict } from "../api/types";

const cardFor = (name: string) =>
  screen.getByRole("heading", { name }).closest("li") as HTMLElement;

describe("AgentCards", () => {
  it("renders six idle cards before any run", () => {
    render(<AgentCards verdicts={[]} phase="idle" />);
    expect(screen.getAllByRole("heading", { level: 4 })).toHaveLength(6);
    expect(screen.getAllByText("Standing by")).toHaveLength(6);
  });

  it("shows evaluating while the POST is in flight", () => {
    render(<AgentCards verdicts={[]} phase="evaluating" />);
    expect(screen.getAllByText("Evaluating")).toHaveLength(6);
  });

  it("shows waiting for agents without a verdict yet", () => {
    const verdicts: AgentVerdict[] = [{ agent: "risk", score: 0.12, hint: "APPROVE" }];
    render(<AgentCards verdicts={verdicts} phase="verdicts_pending" />);
    expect(within(cardFor("Risk")).getByText("Verdict received")).toBeInTheDocument();
    expect(within(cardFor("Fraud")).getByText("Waiting for verdict")).toBeInTheDocument();
  });

  it("shows missing for agents with no stored verdict once settled", () => {
    const verdicts: AgentVerdict[] = [{ agent: "risk", score: 0.12, hint: "APPROVE" }];
    render(<AgentCards verdicts={verdicts} phase="partial" />);
    expect(within(cardFor("Policy")).getByText("No verdict stored yet")).toBeInTheDocument();
  });

  it("marks degraded via degraded_agents and via verdict.degraded", () => {
    const verdicts: AgentVerdict[] = [
      { agent: "risk", score: 0.1, hint: "APPROVE" },
      { agent: "fraud", score: 0.2, hint: "APPROVE", degraded: true },
    ];
    render(<AgentCards verdicts={verdicts} phase="partial" degradedAgents={["risk"]} />);
    expect(within(cardFor("Risk")).getByText("Degraded")).toBeInTheDocument();
    expect(within(cardFor("Fraud")).getByText("Degraded")).toBeInTheDocument();
    expect(within(cardFor("Fraud")).getByText(/Templated explanation/)).toBeInTheDocument();
  });

  it("badges VETO on policy and fraud only, ADVISORY on the other three", () => {
    render(<AgentCards verdicts={[]} phase="idle" />);
    for (const name of ["Policy", "Fraud"]) {
      expect(within(cardFor(name)).getByText(/VETO capable/)).toBeInTheDocument();
    }
    for (const name of ["Routing", "Merchant", "Personalization"]) {
      expect(within(cardFor(name)).getByText(/ADVISORY/)).toBeInTheDocument();
      expect(within(cardFor(name)).queryByText(/VETO/)).toBeNull();
    }
    expect(within(cardFor("Risk")).queryByText(/VETO|ADVISORY/)).toBeNull();
  });

  it("highlights drivers", () => {
    const verdicts: AgentVerdict[] = [{ agent: "fraud", score: 0.95, hint: "DECLINE" }];
    render(<AgentCards verdicts={verdicts} phase="complete" drivers={["fraud"]} />);
    expect(within(cardFor("Fraud")).getByText(/Drove this outcome/)).toBeInTheDocument();
    expect(within(cardFor("Risk")).queryByText(/Drove this outcome/)).toBeNull();
  });

  it("shows rationale, confidence and evidence only when the API supplies them", () => {
    const verdicts: AgentVerdict[] = [
      {
        agent: "risk",
        score: 0.1,
        hint: "APPROVE",
        rationale: "Long clean history.",
        confidence: 0.9,
        evidence: [{ signal: "chargebacks", value: 0, weight: 0.3 }],
      },
      { agent: "fraud", score: 0.2, hint: "APPROVE" },
    ];
    render(<AgentCards verdicts={verdicts} phase="complete" />);
    const risk = within(cardFor("Risk"));
    expect(risk.getByText("Reported by this agent")).toBeInTheDocument();
    expect(risk.getByText("Long clean history.")).toBeInTheDocument();
    expect(risk.getByText(/chargebacks: 0 \(0.3\)/)).toBeInTheDocument();
    expect(within(cardFor("Fraud")).queryByText("Reported by this agent")).toBeNull();
  });

  it("always labels the general description", () => {
    render(<AgentCards verdicts={[]} phase="idle" />);
    expect(screen.getAllByText("General description:")).toHaveLength(6);
  });
});
