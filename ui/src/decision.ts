// Presentation-only decision helpers. This maps a decision string to a CSS class name
// for the banner color (APPROVE=green, CHALLENGE=amber, DECLINE=red). It does NOT make
// or re-derive any decision — the backend is the source of truth.

import type { Decision } from "./api/types";

export type DecisionColor = "approve" | "challenge" | "decline" | "unknown";

/** Map a decision to a color class; null/unknown decisions resolve to "unknown". */
export function decisionColor(decision: Decision | null | undefined): DecisionColor {
  switch ((decision ?? "").toUpperCase()) {
    case "APPROVE":
      return "approve";
    case "CHALLENGE":
      return "challenge";
    case "DECLINE":
      return "decline";
    default:
      return "unknown";
  }
}

/** A short human label for a decision (falls back to "Pending" when unknown). */
export function decisionLabel(decision: Decision | null | undefined): string {
  switch ((decision ?? "").toUpperCase()) {
    case "APPROVE":
      return "APPROVE";
    case "CHALLENGE":
      return "CHALLENGE";
    case "DECLINE":
      return "DECLINE";
    default:
      return "Pending";
  }
}
