// Copy for the six Decision Journey stages (plan 5.2). Thresholds come from the single
// thresholds module and are always described as defaults.
import type { IconName } from "../components/ui/Icon";
import {
  APPROVE_MAX,
  CHALLENGE_MAX,
  DECISION_DEADLINE_MS,
  FRAUD_BLOCK,
  W_FRAUD,
  W_RISK,
} from "../config/thresholds";
import type { TooltipKey } from "./tooltips";

export interface StageContent {
  id: number;
  title: string;
  summary: string;
  how: string;
  icon: IconName;
  /** Terms explained with an InfoTip next to the how-it-works text. */
  terms: { label: string; key: TooltipKey }[];
}

export const STAGE_CONTENT: StageContent[] = [
  {
    id: 1,
    title: "Checkout received",
    summary: "Your checkout arrives at the front door.",
    how: "checkout-api checks the request, gives it a transaction ID and a trace ID, and checks the idempotency key so a retry never charges twice. Then it hands the checkout to the orchestrator.",
    icon: "receipt",
    terms: [
      { label: "Idempotency key", key: "idempotencyKey" },
      { label: "Trace ID", key: "traceId" },
    ],
  },
  {
    id: 2,
    title: "Shared representation built",
    summary: "One unified view of the transaction, built once.",
    how: "Before any agent looks at the checkout, the orchestrator builds one shared representation: the transaction's features plus signals from the Neo4j graph, such as devices shared with other customers, and fast counters from Redis. All six agents read this same view, so they never disagree about the facts.",
    icon: "layers",
    terms: [{ label: "Shared representation", key: "sharedRepresentation" }],
  },
  {
    id: 3,
    title: "Six agents evaluate in parallel",
    summary: "Six specialists review the same facts at the same time.",
    how: `Each agent answers its own question with a fast ML score. None waits for another. If an agent is slow, the decision engine moves on after a short deadline (default ${DECISION_DEADLINE_MS} ms) using safe defaults.`,
    icon: "network",
    terms: [
      { label: "Degraded", key: "degraded" },
      { label: "Advisory", key: "advisory" },
    ],
  },
  {
    id: 4,
    title: "Decision engine aggregates",
    summary: "Safety rules first, then a weighted score.",
    how: `1. Hard vetoes first: if Policy denies, or the Fraud score is ${FRAUD_BLOCK} or higher, the answer is DECLINE straight away. 2. Otherwise it blends Risk and Fraud into a composite score: ${W_RISK} x risk + ${W_FRAUD} x fraud. At or below ${APPROVE_MAX} is APPROVE, up to ${CHALLENGE_MAX.toFixed(2)} is CHALLENGE, above that is DECLINE. 3. Merchant rules can raise an APPROVE to a CHALLENGE. 4. Personalization only suggests a payment method; it never changes the outcome. These are default thresholds; your deployment may change them.`,
    icon: "scale",
    terms: [
      { label: "Veto", key: "veto" },
      { label: "Composite score", key: "compositeScore" },
      { label: "Decision engine", key: "decisionEngine" },
    ],
  },
  {
    id: 5,
    title: "Route and execute",
    summary: "Pick the healthiest processor, keep the rest as backup.",
    how: "The Routing agent scores every payment processor on predicted success, cost and speed. The best one is chosen and the others are kept in order for failover if it fails. The charge is sent to a simulated processor, so no real money moves. Only APPROVE attempts a charge.",
    icon: "route",
    terms: [
      { label: "Failover", key: "failover" },
      { label: "Simulated processor", key: "simulatedProcessor" },
    ],
  },
  {
    id: 6,
    title: "Recorded",
    summary: "Everything is written down, so it can be explained later.",
    how: "Each step is saved as an event in the event log in Kafka, and nothing is overwritten. A projector copies it into the Neo4j graph, so future checkouts learn from this one, and into Postgres, the audit trail behind this screen. The trace ID ties all the logs together.",
    icon: "lock",
    terms: [
      { label: "Event log", key: "eventLog" },
      { label: "Trace ID", key: "traceId" },
    ],
  },
];
