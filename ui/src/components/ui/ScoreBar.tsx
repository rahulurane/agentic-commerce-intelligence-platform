import { formatScore } from "../../lib/format";

interface Props {
  label: string;
  /** 0-1 score; null renders an empty bar with "n/a". */
  value: number | null;
  /** Optional marker position (0-1), e.g. the default fraud block threshold. */
  tick?: number;
  tickLabel?: string;
}

/** Horizontal 0-1 score bar with a numeric readout. */
export default function ScoreBar({ label, value, tick, tickLabel }: Props) {
  const pct = value == null ? 0 : Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="scorebar">
      <div className="scorebar__label">
        <span>{label}</span>
        <span className="scorebar__value">{formatScore(value)}</span>
      </div>
      <div
        className="scorebar__track"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={value ?? undefined}
        aria-valuetext={value == null ? "no score" : formatScore(value)}
      >
        <div className="scorebar__fill" style={{ width: `${pct}%` }} />
        {tick != null && (
          <span
            className="scorebar__tick"
            style={{ left: `${tick * 100}%` }}
            title={tickLabel}
            aria-hidden="true"
          />
        )}
      </div>
    </div>
  );
}
