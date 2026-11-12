import { useId, useState } from "react";
import type { CheckoutRequest } from "../../api/types";
import { TOOLTIPS } from "../../content/tooltips";
import Disclosure from "../ui/Disclosure";
import InfoTip from "../ui/InfoTip";

interface Props {
  onSubmit: (body: CheckoutRequest) => void;
  disabled: boolean;
}

const METHOD_TYPES = ["upi", "card", "wallet", "netbanking"];

type Errors = Partial<Record<"merchant" | "customer" | "amount" | "currency", string>>;

function validate(values: {
  merchantId: string;
  customerId: string;
  amount: string;
  currency: string;
}): Errors {
  const errors: Errors = {};
  if (!values.merchantId.trim()) errors.merchant = "Merchant is required.";
  if (!values.customerId.trim()) errors.customer = "Customer is required.";
  const amount = Number.parseFloat(values.amount);
  if (!(amount > 0)) errors.amount = "Amount must be greater than 0.";
  if (!/^[A-Za-z]{3}$/.test(values.currency.trim())) {
    errors.currency = "Currency must be 3 letters, for example INR.";
  }
  return errors;
}

/** A free-form checkout form for running an ad-hoc transaction (not a seeded scenario). */
export default function CheckoutForm({ onSubmit, disabled }: Props) {
  const uid = useId();
  const [merchantId, setMerchantId] = useState("mrc_demo");
  const [customerId, setCustomerId] = useState("cus_clean");
  const [amount, setAmount] = useState("120.0");
  const [currency, setCurrency] = useState("INR");
  const [methodType, setMethodType] = useState("upi");
  const [deviceFingerprint, setDeviceFingerprint] = useState("dev_clean");
  const [errors, setErrors] = useState<Errors>({});

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const found = validate({ merchantId, customerId, amount, currency });
    setErrors(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    const body: CheckoutRequest = {
      merchant_id: merchantId.trim(),
      customer_id: customerId.trim(),
      amount: Number.parseFloat(amount),
      currency: currency.trim().toUpperCase(),
      payment_method: { type: methodType, token: `tok_${customerId.trim()}` },
      context: {
        device_fingerprint: deviceFingerprint,
        ip: "203.0.113.9",
        user_agent: "acip-demo/1.0",
      },
      idempotency_key: `idem_form_${Date.now()}`,
    };
    onSubmit(body);
  }

  const field = (key: keyof Errors) => ({
    "aria-invalid": errors[key] ? true : undefined,
    "aria-describedby": errors[key] ? `${uid}-${key}-err` : undefined,
  });
  const err = (key: keyof Errors) =>
    errors[key] ? (
      <span id={`${uid}-${key}-err`} className="field__error">
        {errors[key]}
      </span>
    ) : null;

  return (
    <section className="card checkout-form">
      <Disclosure title="Custom checkout">
        <form onSubmit={handleSubmit} noValidate>
          <div className="field">
            <label className="field__label" htmlFor={`${uid}-merchant`}>
              Merchant
            </label>
            <input
              id={`${uid}-merchant`}
              value={merchantId}
              onChange={(e) => setMerchantId(e.target.value)}
              {...field("merchant")}
            />
            {err("merchant")}
          </div>
          <div className="field">
            <label className="field__label" htmlFor={`${uid}-customer`}>
              Customer
            </label>
            <input
              id={`${uid}-customer`}
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              {...field("customer")}
            />
            {err("customer")}
          </div>
          <div className="field">
            <label className="field__label" htmlFor={`${uid}-amount`}>
              Amount
            </label>
            <input
              id={`${uid}-amount`}
              type="number"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              {...field("amount")}
            />
            {err("amount")}
          </div>
          <div className="field">
            <label className="field__label" htmlFor={`${uid}-currency`}>
              Currency
            </label>
            <input
              id={`${uid}-currency`}
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              {...field("currency")}
            />
            {err("currency")}
          </div>
          <div className="field">
            <label className="field__label" htmlFor={`${uid}-method`}>
              Payment method
            </label>
            <select
              id={`${uid}-method`}
              value={methodType}
              onChange={(e) => setMethodType(e.target.value)}
            >
              {METHOD_TYPES.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <span className="field__label">
              <label htmlFor={`${uid}-device`}>Device fingerprint</label>
              <InfoTip term="device fingerprint" text={TOOLTIPS.deviceFingerprint} />
            </span>
            <input
              id={`${uid}-device`}
              value={deviceFingerprint}
              onChange={(e) => setDeviceFingerprint(e.target.value)}
            />
          </div>
          <p className="muted" style={{ marginBottom: "var(--space-3)" }}>
            Each run gets a fresh idempotency key
            <InfoTip term="idempotency key" text={TOOLTIPS.idempotencyKey} />
          </p>
          <button type="submit" className="btn btn--primary" disabled={disabled}>
            Run custom checkout
          </button>
        </form>
      </Disclosure>
    </section>
  );
}
