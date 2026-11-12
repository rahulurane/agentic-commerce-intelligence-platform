import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, statusText: "OK", json: async () => body } as Response;
}

function checkoutBody(over: Record<string, unknown> = {}) {
  return {
    transaction_id: "txn_ok",
    decision: "APPROVE",
    route: "processor_a",
    composite_score: 0.1,
    explanation: "composite 0.10 = 0.50*risk 0.10 + 0.50*fraud 0.10; banded to APPROVE.",
    recommended_method: "upi",
    partial: false,
    degraded_agents: [],
    route_alternatives: [],
    verdicts: {},
    trace_id: "t1",
    ...over,
  };
}

function txBody(n: number) {
  const agents = ["risk", "fraud", "routing", "policy", "merchant", "checkout_personalization"];
  return {
    transaction_id: "txn_ok",
    customer_id: "cus_clean",
    amount: 120,
    status: "APPROVED",
    decision: "APPROVE",
    composite_score: 0.1,
    strategy: "weighted_veto",
    verdicts: agents.slice(0, n).map((agent) => ({ agent, score: 0.1, hint: "APPROVE" })),
    created_at: null,
  };
}

function routedFetch(fn: ReturnType<typeof vi.fn>, checkout: unknown, tx: unknown) {
  return fn.mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/healthz")) return jsonResponse({ status: "ok" });
    if (url.includes("/v1/checkout")) return jsonResponse(checkout);
    return jsonResponse(tx);
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("App", () => {
  it("shows a clear error when the checkout-api is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    const user = userEvent.setup();
    render(<App />);

    // Run the first scenario button.
    const buttons = screen.getAllByRole("button", { name: /clean shopper/i });
    await user.click(buttons[0]);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/could not reach checkout-api/i);
    });
  });

  it("renders outcome, why and journey after a successful checkout", async () => {
    vi.stubGlobal("fetch", routedFetch(vi.fn(), checkoutBody(), txBody(1)));
    const user = userEvent.setup();
    const { container } = render(<App />);
    await user.click(screen.getAllByRole("button", { name: /clean shopper/i })[0]);

    await waitFor(() => expect(screen.getAllByText("txn_ok").length).toBeGreaterThan(0));
    expect(screen.getByRole("heading", { name: "APPROVE" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Why this decision" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Decision journey" })).toBeInTheDocument();
    expect(screen.getByText(/this is a replay, not live timing/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show all now" }));
    await waitFor(() => expect(screen.getByText("1 of 6 verdicts received.")).toBeInTheDocument());
    expect(container.querySelectorAll("li.stage")).toHaveLength(6);
    expect(screen.getByText("Verdict received")).toBeInTheDocument();
    expect(screen.getAllByText("No verdict stored yet")).toHaveLength(5);
  });

  it("shows an indeterminate evaluating state while the POST is pending", async () => {
    let release: (r: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => {
      release = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/v1/checkout")) return pending;
        return jsonResponse({ status: "ok" });
      }),
    );
    const user = userEvent.setup();
    const { container } = render(<App />);
    await user.click(screen.getAllByRole("button", { name: /clean shopper/i })[0]);

    await waitFor(() => expect(container.querySelectorAll("li.stage--evaluating")).toHaveLength(6));
    expect(container.querySelectorAll("li.stage[aria-busy='true']")).toHaveLength(6);
    expect(screen.getAllByText("Evaluating checkout").length).toBeGreaterThan(0);
    expect(screen.queryByText(/Round trip/)).toBeNull();

    release(jsonResponse(checkoutBody()));
    await waitFor(() => expect(screen.getAllByText("txn_ok").length).toBeGreaterThan(0));
  });

  it("shows missing cards, a partial notice and Retry fetch when verdicts are empty", async () => {
    vi.stubGlobal("fetch", routedFetch(vi.fn(), checkoutBody(), txBody(0)));
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getAllByRole("button", { name: /clean shopper/i })[0]);

    await waitFor(
      () => expect(screen.getByRole("button", { name: "Retry fetch" })).toBeInTheDocument(),
      { timeout: 5000 },
    );
    expect(screen.getByText(/Some agents did not report in time/)).toBeInTheDocument();
    expect(screen.getByText("0 of 6 verdicts received.")).toBeInTheDocument();
    expect(
      screen.getByText("Not confirmed yet: no agent verdicts have arrived."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("No verdict stored yet")).toHaveLength(6);
  }, 10000);

  it("shows a partial result with the verdicts that did arrive", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch(vi.fn(), checkoutBody({ partial: true, degraded_agents: ["risk"] }), txBody(3)),
    );
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getAllByRole("button", { name: /clean shopper/i })[0]);

    await waitFor(() => expect(screen.getByText("Partial")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Show all now" }));
    expect(screen.getByText("3 of 6 verdicts received.")).toBeInTheDocument();
    expect(screen.getByText(/Degraded: risk\./)).toBeInTheDocument();
  });

  it("shows the empty state and a connected pill on load", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          ({
            ok: true,
            status: 200,
            statusText: "OK",
            json: async () => ({ status: "ok" }),
          }) as Response,
      ),
    );
    render(<App />);
    expect(screen.getByText("Start here")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Decision Intelligence" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Connected")).toBeInTheDocument());
  });

  it("shows an unreachable pill with Retry when /healthz fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    render(<App />);
    await waitFor(() => expect(screen.getByText("Cannot reach checkout-api")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
