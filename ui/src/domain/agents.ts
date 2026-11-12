// Static, plain-English description of the six agents (plan 5.4). Presentation data only.
import type { IconName } from "../components/ui/Icon";
import { W_FRAUD, W_RISK } from "../config/thresholds";

export type AgentKey =
  | "risk"
  | "fraud"
  | "routing"
  | "policy"
  | "merchant"
  | "checkout_personalization";

export type AgentPower = "veto" | "advisory";

export interface AgentInfo {
  key: AgentKey;
  name: string;
  role: string;
  looksAt: string;
  icon: IconName;
  power: AgentPower;
  /** Badges shown on the card, in order. */
  badges: string[];
}

const pct = (w: number) => `Scores ${Math.round(w * 100)}%`;

export const AGENTS: AgentInfo[] = [
  {
    key: "risk",
    name: "Risk",
    role: "Judges how likely this customer is to cause a loss.",
    looksAt: "Customer history, spending speed, past chargebacks, amount compared with normal.",
    icon: "scale",
    power: "advisory",
    badges: [pct(W_RISK)],
  },
  {
    key: "fraud",
    name: "Fraud",
    role: "Spots signs of fraud, including fraud rings.",
    looksAt: "Shared devices, linked accounts in the graph, IP and location, bursts of activity.",
    icon: "network",
    power: "veto",
    badges: ["VETO capable", pct(W_FRAUD)],
  },
  {
    key: "routing",
    name: "Routing",
    role: "Chooses the best payment processor.",
    looksAt: "Each processor's success rate, cost and speed, and the merchant's preference.",
    icon: "route",
    power: "advisory",
    badges: ["ADVISORY: picks the route"],
  },
  {
    key: "policy",
    name: "Policy",
    role: "Enforces compliance and merchant rules.",
    looksAt: "Identity checks, sanctions flags, merchant limits, geography rules.",
    icon: "shield",
    power: "veto",
    badges: ["VETO capable"],
  },
  {
    key: "merchant",
    name: "Merchant",
    role: "Applies the merchant's own preferences.",
    looksAt: "The merchant's risk appetite, allowed payment methods and overrides.",
    icon: "receipt",
    power: "advisory",
    badges: ["ADVISORY: can request step-up"],
  },
  {
    key: "checkout_personalization",
    name: "Personalization",
    role: "Suggests the payment method most likely to work for this customer.",
    looksAt: "The customer's past success with each payment method.",
    icon: "wallet",
    power: "advisory",
    badges: ["ADVISORY: never changes the outcome"],
  },
];

export const AGENT_KEYS: AgentKey[] = AGENTS.map((a) => a.key);

export function agentInfo(key: string): AgentInfo | undefined {
  return AGENTS.find((a) => a.key === key);
}
