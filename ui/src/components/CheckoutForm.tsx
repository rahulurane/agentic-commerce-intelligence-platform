import { useState } from "react";
import type { CheckoutRequest } from "../api/types";

interface Props {
  onSubmit: (body: CheckoutRequest) => void;
  disabled: boolean;
}

const METHOD_TYPES = ["upi", "card", "wallet", "netbanking"];

/** A free-form checkout form for running an ad-hoc transaction (not a seeded scenario). */
export default function CheckoutForm({ onSubmit, disabled }: Props) {
  const [merchantId, setMerchantId] = useState("mrc_demo");
  const [customerId, setCustomerId] = useState("cus_clean");
  const [amount, setAmount] = useState("120.0");
  const [currency, setCurrency] = useState("INR");
  const [methodType, setMethodType] = useState("upi");
  const [deviceFingerprint, setDeviceFingerprint] = useState("dev_clean");

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const body: CheckoutRequest = {
      merchant_id: merchantId,
      customer_id: customerId,
      amount: Number.parseFloat(amount) || 0,
      currency,
      payment_method: { type: methodType, token: `tok_${customerId}` },
      context: {
        device_fingerprint: deviceFingerprint,
        ip: "203.0.113.9",
        user_agent: "acip-demo/1.0",
      },
      idempotency_key: `idem_form_${Date.now()}`,
    };
    onSubmit(body);
  }

  return (
    <section className="checkout-form">
      <h2>Custom checkout</h2>
      <form onSubmit={handleSubmit}>
        <label>
          Merchant
          <input
            value={merchantId}
            onChange={(e) => setMerchantId(e.target.value)}
          />
        </label>
        <label>
          Customer
          <input
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
          />
        </label>
        <label>
          Amount
          <input
            type="number"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </label>
        <label>
          Currency
          <input value={currency} onChange={(e) => setCurrency(e.target.value)} />
        </label>
        <label>
          Payment method
          <select
            value={methodType}
            onChange={(e) => setMethodType(e.target.value)}
          >
            {METHOD_TYPES.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label>
          Device fingerprint
          <input
            value={deviceFingerprint}
            onChange={(e) => setDeviceFingerprint(e.target.value)}
          />
        </label>
        <button type="submit" className="primary" disabled={disabled}>
          Run checkout
        </button>
      </form>
    </section>
  );
}
