// Guided tour copy (plan 5.7). `target` matches a data-tour attribute in the page.
export interface TourStep {
  target: "brand" | "launcher" | "journey" | "agents" | "outcome" | "help";
  text: string;
}

export const TOUR_STEPS: TourStep[] = [
  {
    target: "brand",
    text: "Welcome to ACIP. This takes under a minute. We will show you how every checkout gets decided.",
  },
  {
    target: "launcher",
    text: "Start here. Each card is a ready-made story. Press Run on one to send a checkout.",
  },
  {
    target: "journey",
    text: "This is the decision journey. Six steps from 'received' to 'recorded'. Open any step to see what happened and how it works.",
  },
  {
    target: "agents",
    text: "Six specialist agents review the same facts in parallel. Cards marked VETO can stop a payment on their own.",
  },
  {
    target: "outcome",
    text: "The outcome and a plain-English reason appear here. Green approves, amber asks for extra verification, red declines. Each also has an icon and a word.",
  },
  {
    target: "help",
    text: "Stuck on a term? Press the Help button or the ? key any time. You can replay this tour from there.",
  },
];
