// The five canonical demo scenarios, mirroring scripts/demo.py._request_body +
// scripts/seed.py.SCENARIOS exactly: merchant_id='mrc_demo', currency='INR',
// context.ip='203.0.113.9', context.user_agent='acip-demo/1.0',
// context.device_fingerprint=<device_id>, payment_method.token='tok_<name>',
// idempotency_key='idem_demo_<name>'. The expected decision is shown in the UI as a hint.

import type { CheckoutRequest } from "./api/types";
import type { IconName } from "./components/ui/Icon";

export interface Scenario {
  /** Stable scenario name (matches seed.py). */
  name: string;
  /** Human-friendly label for the button. */
  label: string;
  /** The expected decision, for display only (the backend is the source of truth). */
  expected: "APPROVE" | "CHALLENGE" | "DECLINE";
  /** One-line description of what the scenario demonstrates. */
  blurb: string;
  /** Display only: icon, short story and what the scenario demonstrates. */
  icon: IconName;
  story: string;
  demonstrates: string;
  customerId: string;
  amount: number;
  methodType: string;
  deviceId: string;
}

export const SCENARIOS: Scenario[] = [
  {
    name: "clean_shopper",
    label: "Clean shopper",
    expected: "APPROVE",
    blurb: "Normal customer with good history — low risk.",
    icon: "user",
    story: "A regular customer buys a small order by UPI.",
    demonstrates: "Low risk flows straight through.",
    customerId: "cus_clean",
    amount: 120.0,
    methodType: "upi",
    deviceId: "dev_clean",
  },
  {
    name: "ring_member",
    label: "Fraud ring member",
    expected: "DECLINE",
    blurb: "Device shared across a fraud ring — fraud veto.",
    icon: "network",
    story: "A card used on a device shared with a ring of accounts.",
    demonstrates: "A fraud veto, found through the graph.",
    customerId: "cus_ring",
    amount: 90.0,
    methodType: "card",
    deviceId: "dev_shared",
  },
  {
    name: "high_value_midrisk",
    label: "High-value mid-risk",
    expected: "CHALLENGE",
    blurb: "Large but legitimate purchase — step up for review.",
    icon: "scale",
    story: "A big card purchase from a customer with one past chargeback.",
    demonstrates: "Borderline cases are stepped up, not blocked.",
    customerId: "cus_midrisk",
    amount: 4800.0,
    methodType: "card",
    deviceId: "dev_midrisk",
  },
  {
    name: "sanctioned_geo",
    label: "Sanctioned geography",
    expected: "DECLINE",
    blurb: "Customer in a blocked region — policy veto.",
    icon: "shield",
    story: "A wallet payment from a blocked region.",
    demonstrates: "A policy veto that no score can override.",
    customerId: "cus_sanctioned",
    amount: 200.0,
    methodType: "wallet",
    deviceId: "dev_sanctioned",
  },
  {
    name: "unhealthy_preferred_route",
    label: "Unhealthy preferred route",
    expected: "APPROVE",
    blurb: "Preferred processor degraded — reroute to a healthy alternate.",
    icon: "route",
    story: "A good customer, but the preferred processor is struggling.",
    demonstrates: "Smart routing with failover.",
    customerId: "cus_reroute",
    amount: 260.0,
    methodType: "card",
    deviceId: "dev_reroute",
  },
];

/**
 * Build the POST /v1/checkout body for a scenario. A nonce suffix is appended to the
 * idempotency_key so re-running the same scenario in a session produces a fresh
 * evaluation rather than an idempotent replay of the first result.
 */
export function scenarioBody(scenario: Scenario, nonce?: string): CheckoutRequest {
  const idem = nonce ? `idem_demo_${scenario.name}_${nonce}` : `idem_demo_${scenario.name}`;
  return {
    merchant_id: "mrc_demo",
    customer_id: scenario.customerId,
    amount: scenario.amount,
    currency: "INR",
    payment_method: {
      type: scenario.methodType,
      token: `tok_${scenario.name}`,
    },
    context: {
      device_fingerprint: scenario.deviceId,
      ip: "203.0.113.9",
      user_agent: "acip-demo/1.0",
    },
    idempotency_key: idem,
  };
}
