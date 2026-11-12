// Presentation formatting helpers.

/** A 0-1 score to three decimals, or an em-free placeholder when missing. */
export function formatScore(score: number | null | undefined): string {
  return score == null ? "n/a" : score.toFixed(3);
}

/** An amount with its currency code, e.g. "120.00 INR". */
export function formatAmount(amount: number | null | undefined, currency?: string): string {
  if (amount == null) {
    return "n/a";
  }
  const value = amount.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return currency ? `${value} ${currency}` : value;
}

/** Milliseconds rounded to a whole number, e.g. "412 ms". */
export function formatMs(ms: number | null | undefined): string {
  return ms == null ? "n/a" : `${Math.round(ms)} ms`;
}

/** Humanise an agent key: "checkout_personalization" -> "checkout personalization". */
export function humanize(key: string): string {
  return key.replace(/_/g, " ");
}
