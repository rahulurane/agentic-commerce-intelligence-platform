// Help drawer copy (plan 5.6). Agents and journey stages are rendered from their own modules.
import { APPROVE_MAX, CHALLENGE_MAX, FRAUD_BLOCK } from "../config/thresholds";

export type HelpKind = "text" | "stages" | "agents" | "outcomes" | "scenarios" | "glossary" | "faq";

export interface HelpSection {
  id: string;
  title: string;
  kind: HelpKind;
  paragraphs?: string[];
}

export const HELP_SECTIONS: HelpSection[] = [
  {
    id: "help-what",
    title: "What is ACIP",
    kind: "text",
    paragraphs: [
      "ACIP decides every checkout before the payment is attempted. Six specialist AI agents look at the same shared facts at the same time. A decision engine combines their answers into APPROVE, CHALLENGE or DECLINE, with a plain-English reason. It runs entirely on open-source tools on this machine. Think commerce made easy, with less complexity and more confidence.",
    ],
  },
  {
    id: "help-read",
    title: "How to read this screen",
    kind: "text",
    paragraphs: [
      "Left: launch a checkout (scenarios, custom form, recent). Right top: the outcome and why. Middle: the decision journey, six steps, open any step to see what happened and how it works. Below: the full trace. Header: connection status, tour, help, theme.",
    ],
  },
  {
    id: "help-journey",
    title: "Decision journey step by step",
    kind: "stages",
    paragraphs: [
      "While a checkout is being evaluated you will see a pulsing Evaluating state. When the result arrives, the steps light up one after another. That is a replay of the real result, not live timing. The only timing shown is the real round trip.",
    ],
  },
  { id: "help-agents", title: "The six agents", kind: "agents" },
  {
    id: "help-outcomes",
    title: "Decision outcomes",
    kind: "outcomes",
    paragraphs: [
      `Score bands (defaults): up to ${APPROVE_MAX} approve, up to ${CHALLENGE_MAX.toFixed(2)} challenge, above that decline. Fraud ${FRAUD_BLOCK} or higher is an automatic decline.`,
    ],
  },
  { id: "help-scenarios", title: "Scenario guide", kind: "scenarios" },
  { id: "help-glossary", title: "Glossary", kind: "glossary" },
  { id: "help-trouble", title: "Troubleshooting", kind: "faq" },
];

export const OUTCOME_HELP: { name: string; text: string }[] = [
  { name: "APPROVE", text: "Low risk. Let it through and send it to the best processor." },
  { name: "CHALLENGE", text: "Borderline. Ask for extra verification first." },
  {
    name: "DECLINE",
    text: "Blocked. Either a hard rule vetoed it or the score is too high. No charge is attempted.",
  },
];

export const SCENARIO_GUIDE: { name: string; text: string }[] = [
  {
    name: "Clean shopper",
    text: "A regular customer with a good UPI history and a small amount. Risk and fraud scores are low, so the composite lands in the approve band. Expect APPROVE.",
  },
  {
    name: "Fraud ring member",
    text: "Shares a device with a ring of linked accounts in the graph. The Fraud agent scores very high and vetoes. Expect DECLINE with no route.",
  },
  {
    name: "High-value mid-risk",
    text: "A legitimate but large card purchase (4,800) from a customer with one past chargeback. Scores sit in the middle, and merchant rules ask for extra verification. Expect CHALLENGE.",
  },
  {
    name: "Sanctioned geography",
    text: "A customer in a blocked region. Policy denies, which is final whatever the scores say. Expect DECLINE.",
  },
  {
    name: "Unhealthy preferred route",
    text: "The merchant's preferred processor is set up as degraded. The customer is fine, so it is approved, and routing picks a healthier processor with the others as failover. Expect APPROVE on an alternate route.",
  },
];

export const TROUBLESHOOTING: { q: string; a: string }[] = [
  {
    q: "Agent cards are empty.",
    a: "Verdicts land a moment after the decision banner. The screen checks for a few seconds. If they still do not appear, the agent services may be busy; run the checkout again.",
  },
  {
    q: "I see 'Cannot reach checkout-api'.",
    a: "Start the platform with ./start.sh (Docker) or ./start-local.sh (local mode), then press Retry. Check http://localhost:8080/healthz.",
  },
  {
    q: "A scenario returned a different decision.",
    a: "Re-seed with make seed, then try again. Free-form checkouts can legitimately land anywhere.",
  },
  {
    q: "Some agents say Degraded.",
    a: "Expected on the local mock AI provider. Scores are valid; only the explanation text is templated.",
  },
  { q: "The tour did not appear.", a: "It shows once. Use Help > Replay tour." },
  {
    q: "Where are the agent explanations?",
    a: "They appear on each card when the API provides them; otherwise the card shows a general description.",
  },
  {
    q: "Where can I see traces?",
    a: "Jaeger at http://localhost:16686, service checkout-api; Neo4j Browser at http://localhost:7474.",
  },
];
