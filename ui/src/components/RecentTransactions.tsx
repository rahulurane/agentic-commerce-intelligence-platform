import type { CheckoutResponse } from "../api/types";
import { decisionColor } from "../decision";

export interface RecentEntry {
  transactionId: string;
  decision: CheckoutResponse["decision"];
  label: string;
}

interface Props {
  entries: RecentEntry[];
  activeId: string | null;
  onSelect: (transactionId: string) => void;
}

/** Session list of recent transactions with click-through to re-inspect one. */
export default function RecentTransactions({
  entries,
  activeId,
  onSelect,
}: Props) {
  if (entries.length === 0) {
    return null;
  }
  return (
    <section className="recent">
      <h2>Recent (this session)</h2>
      <ul className="recent-list">
        {entries.map((e) => (
          <li key={e.transactionId}>
            <button
              type="button"
              className={`recent-item ${decisionColor(e.decision)} ${
                e.transactionId === activeId ? "active" : ""
              }`}
              onClick={() => onSelect(e.transactionId)}
            >
              <span className="recent-label">{e.label}</span>
              <span className="recent-decision">{e.decision ?? "—"}</span>
              <code className="recent-id">{e.transactionId}</code>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
