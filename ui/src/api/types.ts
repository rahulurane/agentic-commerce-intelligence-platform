// TypeScript interfaces mirroring the three checkout-api response shapes the demo UI
// reads (docs/06 §1). These are a thin mirror of the backend contract — no logic lives
// here. The six per-agent verdicts live on TransactionView / ExplainView (fetched via
// GET /v1/transactions/{id}), NOT on CheckoutResponse (whose `verdicts` is always empty).

export type Decision = "APPROVE" | "CHALLENGE" | "DECLINE" | string;

/** One agent's verdict as surfaced by GET /v1/transactions/{id}. */
export interface AgentVerdict {
  agent: string;
  score: number | null;
  hint: string | null;
  // Optional fields supplied by newer checkout-api versions. Older APIs omit them.
  rationale?: string | null;
  confidence?: number | null;
  degraded?: boolean | null;
  model_version?: string | null;
  evidence?: { signal: string; value: unknown; weight?: number | null }[] | null;
}

/** POST /v1/checkout response body. `verdicts` is ALWAYS empty here — poll the GET. */
export interface CheckoutResponse {
  transaction_id: string;
  decision: Decision | null;
  route: string | null;
  composite_score: number | null;
  explanation: string | null;
  recommended_method: string | null;
  partial: boolean;
  degraded_agents: string[];
  route_alternatives: string[];
  verdicts: Record<string, unknown>;
  trace_id: string;
}

/** GET /v1/transactions/{id} view: current state + decision + per-agent verdicts. */
export interface TransactionView {
  transaction_id: string;
  customer_id: string | null;
  amount: number | null;
  status: string | null;
  decision: Decision | null;
  composite_score: number | null;
  strategy: string | null;
  verdicts: AgentVerdict[];
  created_at: string | null;
}

/** GET /v1/transactions/{id}/explain view: the full decision trace. */
export interface ExplainView {
  transaction_id: string;
  inputs: {
    customer_id: string | null;
    amount: number | null;
  };
  verdicts: AgentVerdict[];
  strategy: string | null;
  final_decision: {
    decision: Decision | null;
    composite_score: number | null;
    status: string | null;
  };
}

/** The POST /v1/checkout request body shape (mirrors scripts/demo.py). */
export interface CheckoutRequest {
  merchant_id: string;
  customer_id: string;
  amount: number;
  currency: string;
  payment_method: {
    type: string;
    token: string;
  };
  context: {
    device_fingerprint: string;
    ip?: string;
    user_agent?: string;
  };
  idempotency_key?: string;
}
