import { useState } from "react";
import type {
  CheckoutRequest,
  CheckoutResponse,
  ExplainView as ExplainViewData,
  TransactionView,
} from "./api/types";
import {
  ApiError,
  getExplain,
  getTransaction,
  pollTransaction,
  postCheckout,
} from "./api/client";
import { scenarioBody, type Scenario } from "./scenarios";
import ScenarioButtons from "./components/ScenarioButtons";
import CheckoutForm from "./components/CheckoutForm";
import DecisionBanner from "./components/DecisionBanner";
import AgentCards from "./components/AgentCards";
import RecentTransactions, {
  type RecentEntry,
} from "./components/RecentTransactions";
import ExplainView from "./components/ExplainView";

export default function App() {
  const [decision, setDecision] = useState<CheckoutResponse | null>(null);
  const [transaction, setTransaction] = useState<TransactionView | null>(null);
  const [explain, setExplain] = useState<ExplainViewData | null>(null);
  const [recent, setRecent] = useState<RecentEntry[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runCheckout(body: CheckoutRequest, label: string) {
    setLoading(true);
    setError(null);
    setDecision(null);
    setTransaction(null);
    setExplain(null);
    try {
      const resp = await postCheckout(body);
      setDecision(resp);
      setActiveId(resp.transaction_id);
      setRecent((prev) => [
        { transactionId: resp.transaction_id, decision: resp.decision, label },
        ...prev.filter((e) => e.transactionId !== resp.transaction_id),
      ]);
      setLoading(false);
      // Poll for the per-agent verdicts, tolerating empty/partial/404.
      setPolling(true);
      const view = await pollTransaction(resp.transaction_id);
      if (view) {
        setTransaction(view);
      }
    } catch (err) {
      setError(describeError(err));
      setLoading(false);
    } finally {
      setPolling(false);
    }
  }

  function handleScenario(scenario: Scenario) {
    const nonce = Date.now().toString(36);
    void runCheckout(scenarioBody(scenario, nonce), scenario.label);
  }

  function handleForm(body: CheckoutRequest) {
    void runCheckout(body, `custom · ${body.customer_id}`);
  }

  async function handleSelect(transactionId: string) {
    setActiveId(transactionId);
    setError(null);
    setExplain(null);
    setPolling(true);
    try {
      const view = await getTransaction(transactionId);
      setTransaction(view);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setTransaction(null);
      } else {
        setError(describeError(err));
      }
    } finally {
      setPolling(false);
    }
  }

  async function handleExplain() {
    if (!activeId) {
      return;
    }
    setError(null);
    try {
      const view = await getExplain(activeId);
      setExplain(view);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setExplain(null);
      } else {
        setError(describeError(err));
      }
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>ACIP — Agentic Commerce Intelligence</h1>
        <p className="muted">
          Six specialist agents decide every checkout in real time. Pick a scenario
          below or run a custom checkout.
        </p>
      </header>

      <main className="layout">
        <div className="col-left">
          <ScenarioButtons onRun={handleScenario} disabled={loading || polling} />
          <CheckoutForm onSubmit={handleForm} disabled={loading || polling} />
          <RecentTransactions
            entries={recent}
            activeId={activeId}
            onSelect={handleSelect}
          />
        </div>

        <div className="col-right">
          {error && (
            <div className="error" role="alert">
              <strong>Could not reach checkout-api.</strong> {error}
            </div>
          )}

          {loading && <div className="loading">Submitting checkout…</div>}

          {decision && <DecisionBanner decision={decision} />}

          {(decision || transaction) && (
            <AgentCards
              verdicts={transaction?.verdicts ?? []}
              waiting={polling}
            />
          )}

          {activeId && (
            <div className="explain-actions">
              <button type="button" onClick={() => void handleExplain()}>
                Show decision trace
              </button>
            </div>
          )}

          {explain && <ExplainView explain={explain} />}

          {!decision && !transaction && !loading && !error && (
            <div className="empty">
              Run a scenario to see the decision, the six agent verdicts, and the full
              explanation.
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    return `HTTP ${err.status}. Is the checkout-api running and reachable?`;
  }
  if (err instanceof Error) {
    return `${err.message}. Is the checkout-api running and reachable?`;
  }
  return "Unknown error.";
}
