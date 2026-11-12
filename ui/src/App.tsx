import { useMemo } from "react";
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

export default function App() {
  const { state, runCheckout, selectRecent, refetchVerdicts, loadExplain, setReplayIndex } =
    useCheckoutRun();
  const { phase, explain, error, activeId } = state;

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
    <div className="app">
      <AppHeader />
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
          {state.notFound && <div className="card">No stored record yet for this transaction.</div>}
          {phase === "idle" && !state.notFound && !state.loadingHistory && <EmptyState />}
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
  );
}
