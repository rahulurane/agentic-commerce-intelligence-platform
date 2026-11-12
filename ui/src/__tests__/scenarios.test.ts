import { describe, expect, it } from "vitest";
import { SCENARIOS, scenarioBody } from "../scenarios";

describe("scenario payloads", () => {
  it("defines the five canonical scenarios", () => {
    expect(SCENARIOS.map((s) => s.name)).toEqual([
      "clean_shopper",
      "ring_member",
      "high_value_midrisk",
      "sanctioned_geo",
      "unhealthy_preferred_route",
    ]);
  });

  it("builds the clean_shopper body matching the canonical demo request", () => {
    const clean = SCENARIOS.find((s) => s.name === "clean_shopper")!;
    const body = scenarioBody(clean);
    expect(body).toEqual({
      merchant_id: "mrc_demo",
      customer_id: "cus_clean",
      amount: 120.0,
      currency: "INR",
      payment_method: { type: "upi", token: "tok_clean_shopper" },
      context: {
        device_fingerprint: "dev_clean",
        ip: "203.0.113.9",
        user_agent: "acip-demo/1.0",
      },
      idempotency_key: "idem_demo_clean_shopper",
    });
  });

  it("builds the ring_member body with the shared device and card method", () => {
    const ring = SCENARIOS.find((s) => s.name === "ring_member")!;
    const body = scenarioBody(ring);
    expect(body.customer_id).toBe("cus_ring");
    expect(body.amount).toBe(90.0);
    expect(body.payment_method).toEqual({ type: "card", token: "tok_ring_member" });
    expect(body.context.device_fingerprint).toBe("dev_shared");
    expect(body.idempotency_key).toBe("idem_demo_ring_member");
  });

  it("appends a nonce to the idempotency key when provided", () => {
    const clean = SCENARIOS.find((s) => s.name === "clean_shopper")!;
    const body = scenarioBody(clean, "abc123");
    expect(body.idempotency_key).toBe("idem_demo_clean_shopper_abc123");
  });

  it("mirrors every scenario's canonical fields", () => {
    const expected: Record<string, [string, number, string, string]> = {
      clean_shopper: ["cus_clean", 120.0, "upi", "dev_clean"],
      ring_member: ["cus_ring", 90.0, "card", "dev_shared"],
      high_value_midrisk: ["cus_midrisk", 4800.0, "card", "dev_midrisk"],
      sanctioned_geo: ["cus_sanctioned", 200.0, "wallet", "dev_sanctioned"],
      unhealthy_preferred_route: ["cus_reroute", 260.0, "card", "dev_reroute"],
    };
    for (const s of SCENARIOS) {
      const body = scenarioBody(s);
      const [cust, amt, method, device] = expected[s.name];
      expect(body.customer_id).toBe(cust);
      expect(body.amount).toBe(amt);
      expect(body.payment_method.type).toBe(method);
      expect(body.payment_method.token).toBe(`tok_${s.name}`);
      expect(body.context.device_fingerprint).toBe(device);
      expect(body.merchant_id).toBe("mrc_demo");
      expect(body.currency).toBe("INR");
    }
  });

  it("keeps display-only fields out of the request body", () => {
    for (const s of SCENARIOS) {
      const body = scenarioBody(s, "n1") as unknown as Record<string, unknown>;
      expect(Object.keys(body).sort()).toEqual([
        "amount",
        "context",
        "currency",
        "customer_id",
        "idempotency_key",
        "merchant_id",
        "payment_method",
      ]);
      expect(body).not.toHaveProperty("story");
      expect(body).not.toHaveProperty("icon");
      expect(s.story.length).toBeGreaterThan(0);
      expect(s.demonstrates.length).toBeGreaterThan(0);
    }
  });
});
