// Glossary entries for the help drawer (plan 5.6 section 7). Text reuses the InfoTip copy.
import { TOOLTIPS } from "./tooltips";

export interface GlossaryEntry {
  term: string;
  text: string;
}

export const GLOSSARY: GlossaryEntry[] = [
  { term: "Shared representation", text: TOOLTIPS.sharedRepresentation },
  { term: "Composite score", text: TOOLTIPS.compositeScore },
  { term: "Veto", text: TOOLTIPS.veto },
  { term: "Challenge (step-up)", text: TOOLTIPS.challenge },
  { term: "Route and failover", text: `${TOOLTIPS.route} ${TOOLTIPS.failover}` },
  { term: "Idempotency", text: TOOLTIPS.idempotencyKey },
  { term: "Trace ID", text: TOOLTIPS.traceId },
  { term: "Event log", text: TOOLTIPS.eventLog },
  { term: "Verdict", text: "One agent's score and hint." },
];
