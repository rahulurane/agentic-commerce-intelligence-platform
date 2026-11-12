// InfoTip copy (plan 5.5). Keys are used by <InfoTip term text>.
export const TOOLTIPS = {
  sharedRepresentation:
    "One unified view of the transaction (its features plus graph signals), built once and read by every agent.",
  compositeScore:
    "A single number from 0 to 1 that blends the Risk and Fraud scores. Lower is safer.",
  veto: "A rule that ends the evaluation immediately. Policy deny or a very high Fraud score both veto.",
  challenge:
    "Not a no. The customer is asked for extra verification, such as a one-time code, before the payment is allowed.",
  decline: "The payment is blocked and no charge is attempted.",
  route: "The payment processor chosen to carry this charge.",
  failover: "If the chosen processor fails, the next one in the list is tried automatically.",
  idempotencyKey:
    "A unique key for one checkout attempt. Sending the same key again returns the same result instead of charging twice.",
  traceId:
    "An ID that follows this checkout through every service. Use it to find its logs and traces.",
  eventLog:
    "A permanent, ordered record of everything that happened (Kafka). Nothing is overwritten.",
  decisionEngine: "The service that turns six verdicts into one decision.",
  degraded: "The agent's score is valid, but its written explanation fell back to a template.",
  advisory: "This agent informs the decision or the route but cannot block a payment.",
  roundTrip: "Time from sending the request to receiving the decision, measured in your browser.",
  simulatedProcessor: "A stand-in for a real payment processor. No real money moves.",
  blockThreshold: "Default setting. Your deployment may change it.",
  approveLimit: "Default setting. Your deployment may change it.",
  challengeLimit: "Default setting. Your deployment may change it.",
  deviceFingerprint:
    "Identifies the buyer's device. Devices shared across many customers raise the Fraud score.",
} as const;

export type TooltipKey = keyof typeof TOOLTIPS;
