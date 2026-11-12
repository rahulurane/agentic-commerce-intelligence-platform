import type { CheckoutRequest } from "./api/types";
import { scenarioBody, type Scenario } from "./scenarios";
import { useCheckoutRun } from "./state/useCheckoutRun";
import AppHeader from "./components/layout/AppHeader";
import ScenarioLauncher from "./components/input/ScenarioLauncher";
import CheckoutForm from "./components/input/CheckoutForm";
import RecentTransactions from "./components/input/RecentTransactions";
import EmptyState from "./components/input/EmptyState";
import DecisionBanner from "./components/DecisionBanner";
import AgentCards from "./components/AgentCards";
import ExplainView from "./components/ExplainView";

export default function App() {
  const { state, runCheckout, selectRecent, loadExplain } = useCheckoutRun();
  const { phase, response, transaction, explain, error, activeId } = state;

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
          {error && (
            <div className="error" role="alert">
              <strong>Could not reach checkout-api.</strong> {error} Start the platform with
              ./start.sh or ./start-local.sh, then retry.
            </div>
          )}
          {evaluating && (
            <div className="loading" role="status">
              <span className="spinner" aria-hidden="true" /> Evaluating checkout…
            </div>
          )}
          {state.notFound && <div className="card">No stored record yet for this transaction.</div>}
          {response && <DecisionBanner decision={response} />}
          {(response || transaction) && (
            <AgentCards verdicts={transaction?.verdicts ?? []} waiting={polling} />
          )}
          {activeId && !state.notFound && (
            <div className="explain-actions">
              <button type="button" className="btn" onClick={() => void loadExplain(activeId)}>
                Show decision trace
              </button>
            </div>
          )}
          {explain && <ExplainView explain={explain} />}
          {phase === "idle" && !state.notFound && !state.loadingHistory && <EmptyState />}
        </div>
      </main>
    </div>
  );
}
