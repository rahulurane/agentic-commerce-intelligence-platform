// Presentation-only decision helpers. This maps a decision string to a CSS class name
// for the banner color (APPROVE=green, CHALLENGE=amber, DECLINE=red), an icon and a tone.
// It does NOT make or re-derive any decision — the backend is the source of truth.
import type { Decision } from "./api/types";
import type { IconName } from "./components/ui/Icon";

export type DecisionColor = "approve" | "challenge" | "decline" | "unknown";
export type DecisionTone = "success" | "warning" | "danger" | "neutral";

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

/** Icon that accompanies a decision so colour is never the only signal. */
export function decisionIcon(decision: Decision | null | undefined): IconName {
  switch (decisionColor(decision)) {
    case "approve":
      return "check-circle";
    case "challenge":
      return "alert-triangle";
    case "decline":
      return "x-circle";
    default:
      return "info";
  }
}

/** Semantic tone for a decision. */
export function decisionTone(decision: Decision | null | undefined): DecisionTone {
  switch (decisionColor(decision)) {
    case "approve":
      return "success";
    case "challenge":
      return "warning";
    case "decline":
      return "danger";
    default:
      return "neutral";
  }
}
