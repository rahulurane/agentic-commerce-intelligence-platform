import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, getHealth, pollTransaction, postCheckout } from "../api/client";
import type { CheckoutRequest, TransactionView } from "../api/types";

const BODY: CheckoutRequest = {
  merchant_id: "mrc_demo",
  customer_id: "cus_clean",
  amount: 120.0,
  currency: "INR",
  payment_method: { type: "upi", token: "tok_clean" },
  context: { device_fingerprint: "dev_clean" },
};

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: String(status),
    json: async () => body,
  } as Response;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("client", () => {
  it("postCheckout returns the decision JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, { transaction_id: "txn_1", decision: "APPROVE" })),
    );
    const resp = await postCheckout(BODY);
    expect(resp.transaction_id).toBe("txn_1");
    expect(resp.decision).toBe("APPROVE");
  });

  it("postCheckout throws ApiError when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(500, {})),
    );
    await expect(postCheckout(BODY)).rejects.toBeInstanceOf(ApiError);
  });

  it("pollTransaction tolerates a 404 then returns verdicts once present", async () => {
    const populated: TransactionView = {
      transaction_id: "txn_1",
      customer_id: "cus_clean",
      amount: 120,
      status: "APPROVED",
      decision: "APPROVE",
      composite_score: 0.1,
      strategy: "weighted_veto",
      verdicts: [{ agent: "risk", score: 0.1, hint: "APPROVE" }],
      created_at: null,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(404, { detail: "not found" }))
      .mockResolvedValueOnce(populated && jsonResponse(200, populated));
    vi.stubGlobal("fetch", fetchMock);

    const view = await pollTransaction("txn_1", 3, 0);
    expect(view?.verdicts).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("pollTransaction returns the last empty view when verdicts never arrive", async () => {
    const empty: TransactionView = {
      transaction_id: "txn_1",
      customer_id: "cus_clean",
      amount: 120,
      status: "PENDING",
      decision: null,
      composite_score: null,
      strategy: null,
      verdicts: [],
      created_at: null,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, empty)),
    );
    const view = await pollTransaction("txn_1", 2, 0);
    expect(view?.verdicts).toHaveLength(0);
  });
});

describe("getHealth", () => {
  it("resolves when /healthz is ok", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(getHealth()).resolves.toBeUndefined();
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toMatch(/\/healthz$/);
  });

  it("rejects with an ApiError on a non-2xx answer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(503, {})),
    );
    await expect(getHealth()).rejects.toBeInstanceOf(ApiError);
  });

  it("aborts the request after the timeout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init?: RequestInit) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => reject(new Error("aborted")));
          }),
      ),
    );
    await expect(getHealth(20)).rejects.toThrow("aborted");
  });
});
