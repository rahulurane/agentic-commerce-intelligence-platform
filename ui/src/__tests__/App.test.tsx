import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";

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
      expect(screen.getByRole("alert")).toHaveTextContent(
        /could not reach checkout-api/i,
      );
    });
  });

  it("renders the decision banner after a successful checkout", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/v1/checkout")) {
        return {
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => ({
            transaction_id: "txn_ok",
            decision: "APPROVE",
            route: "processor_a",
            composite_score: 0.1,
            explanation: "clean",
            recommended_method: "upi",
            partial: false,
            degraded_agents: [],
            route_alternatives: [],
            verdicts: {},
            trace_id: "t1",
          }),
        } as Response;
      }
      // Transaction poll returns verdicts.
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => ({
          transaction_id: "txn_ok",
          customer_id: "cus_clean",
          amount: 120,
          status: "APPROVED",
          decision: "APPROVE",
          composite_score: 0.1,
          strategy: "weighted_veto",
          verdicts: [{ agent: "risk", score: 0.1, hint: "APPROVE" }],
          created_at: null,
        }),
      } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<App />);
    const buttons = screen.getAllByRole("button", { name: /clean shopper/i });
    await user.click(buttons[0]);

    await waitFor(() => {
      // txn_ok appears in both the decision banner and the recent-transactions list.
      expect(screen.getAllByText("txn_ok").length).toBeGreaterThan(0);
    });
    await waitFor(() => {
      expect(screen.getByText("risk")).toBeInTheDocument();
    });
  });
});
