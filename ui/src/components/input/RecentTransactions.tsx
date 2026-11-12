import type { CheckoutResponse } from "../../api/types";
import StatusBadge from "../ui/StatusBadge";

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
export default function RecentTransactions({ entries, activeId, onSelect }: Props) {
  if (entries.length === 0) {
    return null;
  }
  return (
    <section className="card recent" aria-labelledby="recent-title">
      <div className="card__head">
        <h2 id="recent-title">Recent transactions</h2>
      </div>
      <ul className="recent-list">
        {entries.map((e) => (
          <li key={e.transactionId}>
            <button
              type="button"
              className={`recent-item ${e.transactionId === activeId ? "active" : ""}`}
              aria-current={e.transactionId === activeId ? "true" : undefined}
              onClick={() => onSelect(e.transactionId)}
            >
              <span className="recent-label">{e.label}</span>
              <StatusBadge decision={e.decision} />
              <code className="recent-id">{e.transactionId}</code>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
