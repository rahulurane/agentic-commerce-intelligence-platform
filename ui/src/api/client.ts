// Thin HTTP client for the checkout-api. This layer does ONLY HTTP — it never
// re-implements decision logic. The six per-agent verdicts are not in the POST response
// (checkout-api returns an always-empty `verdicts`), so callers POST then poll
// GET /v1/transactions/{id} until the verdicts arrive, tolerating 404 / empty / partial.

import type { CheckoutRequest, CheckoutResponse, ExplainView, TransactionView } from "./types";

// Base URL is injected at build time (Docker) or defaults to the local checkout-api.
const BASE_URL: string =
  (import.meta.env.VITE_CHECKOUT_API_URL as string | undefined) ?? "http://localhost:8080";

/** Error carrying the HTTP status so callers can distinguish 404 from other failures. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseJson<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    throw new ApiError(resp.status, `${resp.status} ${resp.statusText}`);
  }
  return (await resp.json()) as T;
}

/** GET /healthz with a timeout. Resolves when healthy, rejects otherwise. */
export async function getHealth(timeoutMs = 3000): Promise<void> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(`${BASE_URL}/healthz`, { signal: controller.signal });
    if (!resp.ok) {
      throw new ApiError(resp.status, `${resp.status} ${resp.statusText}`);
    }
  } finally {
    clearTimeout(timer);
  }
}

/** POST a checkout and return the immediate decision (verdicts not yet populated). */
export async function postCheckout(body: CheckoutRequest): Promise<CheckoutResponse> {
  const resp = await fetch(`${BASE_URL}/v1/checkout`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseJson<CheckoutResponse>(resp);
}

/** GET the transaction view (current state + decision + verdicts). */
export async function getTransaction(id: string): Promise<TransactionView> {
  const resp = await fetch(`${BASE_URL}/v1/transactions/${encodeURIComponent(id)}`);
  return parseJson<TransactionView>(resp);
}

/** GET the full decision-trace / explain view. */
export async function getExplain(id: string): Promise<ExplainView> {
  const resp = await fetch(`${BASE_URL}/v1/transactions/${encodeURIComponent(id)}/explain`);
  return parseJson<ExplainView>(resp);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Poll GET /v1/transactions/{id} until its verdicts are non-empty or attempts run out.
 *
 * The agents commit their verdicts asynchronously after the POST, and a never-seeded or
 * still-processing id answers 404, so this tolerates 404 and empty/partial verdicts: it
 * returns the last successful view it saw (which may have empty verdicts) rather than
 * throwing, and returns null only if it never got a successful read.
 */
export async function pollTransaction(
  id: string,
  attempts = 5,
  delayMs = 600,
): Promise<TransactionView | null> {
  let last: TransactionView | null = null;
  for (let i = 0; i < attempts; i += 1) {
    try {
      const view = await getTransaction(id);
      last = view;
      if (view.verdicts && view.verdicts.length > 0) {
        return view;
      }
    } catch (err) {
      // A 404 is expected while the transaction is still being persisted; keep polling.
      if (!(err instanceof ApiError && err.status === 404)) {
        throw err;
      }
    }
    if (i < attempts - 1) {
      await delay(delayMs);
    }
  }
  return last;
}
