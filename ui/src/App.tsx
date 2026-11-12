import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CheckoutRequest } from "./api/types";
import { scenarioBody, type Scenario } from "./scenarios";
import { deriveResult } from "./domain/journey";
import { useCheckoutRun } from "./state/useCheckoutRun";
import AppHeader from "./components/layout/AppHeader";
import ScenarioLauncher from "./components/input/ScenarioLauncher";
import CheckoutForm from "./components/input/CheckoutForm";
import RecentTransactions from "./components/input/RecentTransactions";
import EmptyState from "./components/input/EmptyState";
import OutcomeBanner from "./components/journey/OutcomeBanner";
import WhyPanel from "./components/journey/WhyPanel";
import DecisionJourney from "./components/journey/DecisionJourney";
import TraceView from "./components/journey/TraceView";
import GuidedTour from "./components/help/GuidedTour";
import { readStorage, TOUR_DONE_KEY, writeStorage } from "./lib/storage";
import { useHelpShortcut } from "./lib/useHelpShortcut";

const HelpDrawer = lazy(() => import("./components/help/HelpDrawer"));

export default function App() {
  const { state, runCheckout, selectRecent, refetchVerdicts, loadExplain, setReplayIndex } =
    useCheckoutRun();
  const { phase, explain, error, activeId } = state;

  const [helpOpen, setHelpOpen] = useState(false);
  const [tourOpen, setTourOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  const openHelp = useCallback(() => {
    triggerRef.current = document.activeElement as HTMLElement | null;
    setHelpOpen(true);
  }, []);
  const closeHelp = useCallback(() => {
    setHelpOpen(false);
    triggerRef.current?.focus?.();
  }, []);
  const startTour = useCallback(() => {
    setHelpOpen(false);
    setTourOpen(true);
  }, []);
  const closeTour = useCallback(() => {
    writeStorage(TOUR_DONE_KEY, "1");
    setTourOpen(false);
  }, []);
  useHelpShortcut(openHelp, !helpOpen && !tourOpen);

  // The app root is inert while the help dialog is open.
  useEffect(() => {
    const root = rootRef.current;
    if (!root) {
      return;
    }
    if (helpOpen) {
      root.setAttribute("inert", "");
      root.setAttribute("aria-hidden", "true");
    } else {
      root.removeAttribute("inert");
      root.removeAttribute("aria-hidden");
    }
  }, [helpOpen]);

  // First visit: start the tour shortly after load.
  useEffect(() => {
    if (readStorage(TOUR_DONE_KEY)) {
      return;
    }
    const t = setTimeout(() => setTourOpen(true), 600);
    return () => clearTimeout(t);
  }, []);

  const result = useMemo(() => deriveResult(state), [state]);
  const evaluating = phase === "evaluating";
  const polling = phase === "verdicts_pending";
  const busy = evaluating || polling || state.loadingHistory;

  function handleScenario(scenario: Scenario) {
    const nonce = Date.now().toString(36);
    void runCheckout(scenarioBody(scenario, nonce), scenario.label, scenario.name);
  }

  function handleForm(body: CheckoutRequest) {
    void runCheckout(body, `custom · ${body.customer_id}`);
  }

  let announcement = "";
  if (evaluating || state.loadingHistory) {
    announcement = "Evaluating checkout";
  } else if (result?.decision) {
    announcement = `Decision: ${result.decision}. ${result.why.headline}.`;
    if (!polling) {
      announcement += ` Verdicts received: ${result.verdicts.length} of 6.`;
    }
  }

  return (
    <>
      <div className="app" ref={rootRef}>
        <AppHeader onTour={startTour} onHelp={openHelp} />
        <main className="layout">
          <div className="col-left">
            <ScenarioLauncher
              onRun={handleScenario}
              runningName={state.runningKey}
              disabled={busy}
              lastByKey={state.lastByKey}
            />
            <CheckoutForm onSubmit={handleForm} disabled={busy} />
            <RecentTransactions
              entries={state.recent}
              activeId={activeId}
              onSelect={(id) => void selectRecent(id)}
            />
          </div>
          <div className="col-right">
            <div className="sr-only" role="status" aria-live="polite">
              {announcement}
            </div>
            {error && (
              <div className="error" role="alert">
                <strong>Could not reach checkout-api.</strong> {error} Start the platform with
                ./start.sh or ./start-local.sh, then retry.
              </div>
            )}
            {state.notFound && (
              <div className="card">No stored record yet for this transaction.</div>
            )}
            {phase === "idle" && !state.notFound && !state.loadingHistory && (
              <EmptyState onStartTour={startTour} onOpenHelp={openHelp} />
            )}
            <OutcomeBanner
              phase={phase}
              loading={state.loadingHistory}
              result={result}
              roundTripMs={state.roundTripMs}
            />
            {result && result.why.kind !== "pending" && <WhyPanel result={result} />}
            <DecisionJourney
              state={state}
              result={result}
              onReplayIndex={setReplayIndex}
              onRetryFetch={() => {
                if (result) void refetchVerdicts(result.transactionId);
              }}
            />
            {activeId && result && !state.notFound && (
              <TraceView
                transactionId={activeId}
                explain={explain}
                onLoad={() => void loadExplain(activeId)}
              />
            )}
          </div>
        </main>
      </div>
      {helpOpen && (
        <Suspense
          fallback={
            <div className="help-backdrop" role="status">
              <span className="spinner" aria-label="Loading help" />
            </div>
          }
        >
          <HelpDrawer onClose={closeHelp} onReplayTour={startTour} />
        </Suspense>
      )}
      {tourOpen && <GuidedTour onClose={closeTour} />}
    </>
  );
}
