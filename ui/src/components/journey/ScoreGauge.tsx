import { useEffect, useState } from "react";
import { APPROVE_MAX, CHALLENGE_MAX } from "../../config/thresholds";
import { formatScore } from "../../lib/format";

interface Props {
  /** Real composite score (0-1), or null when none was returned. */
  score: number | null;
  /** A veto ended the evaluation: the composite is a sentinel, so the gauge is hidden. */
  veto: boolean;
}

const CX = 100;
const CY = 100;
const R = 80;

/** Point on the semicircle for a 0-1 value (0 = left, 1 = right). */
function point(v: number, radius = R): [number, number] {
  const a = Math.PI * v;
  return [CX - radius * Math.cos(a), CY - radius * Math.sin(a)];
}

function arc(from: number, to: number): string {
  const [x1, y1] = point(from);
  const [x2, y2] = point(to);
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${R} ${R} 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

/** Semicircle gauge with the default approve / challenge / decline bands and a sweeping needle. */
export default function ScoreGauge({ score, veto }: Props) {
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setShown(true), 30);
    return () => clearTimeout(t);
  }, []);

  if (veto) {
    return (
      <div className="gauge gauge--skipped">
        <p className="gauge__skipped-title">Scoring skipped</p>
        <p className="gauge__skipped-text">
          A veto ended the evaluation before a composite score was needed.
        </p>
      </div>
    );
  }

  if (score == null) {
    return (
      <div className="gauge gauge--skipped">
        <p className="gauge__skipped-title">No score</p>
        <p className="gauge__skipped-text">The API did not return a composite score.</p>
      </div>
    );
  }

  const value = Math.max(0, Math.min(1, score));
  const angle = shown ? -90 + 180 * value : -90;
  const label = `Composite score ${formatScore(score)} on a scale of 0 to 1. Default bands: up to ${APPROVE_MAX} approve, up to ${CHALLENGE_MAX.toFixed(2)} challenge, above that decline.`;

  return (
    <div className="gauge">
      <svg viewBox="0 0 200 118" className="gauge__svg" role="img" aria-label={label}>
        <path d={arc(0, APPROVE_MAX)} className="gauge__band gauge__band--approve" />
        <path d={arc(APPROVE_MAX, CHALLENGE_MAX)} className="gauge__band gauge__band--challenge" />
        <path d={arc(CHALLENGE_MAX, 1)} className="gauge__band gauge__band--decline" />
        <g className="gauge__needle" style={{ transform: `rotate(${angle}deg)` }}>
          <line x1={CX} y1={CY} x2={CX} y2={CY - 62} />
          <circle cx={CX} cy={CY} r="6" />
        </g>
        <text x={CX} y="116" textAnchor="middle" className="gauge__value">
          {formatScore(score)}
        </text>
      </svg>
      <p className="gauge__legend">
        Default bands: up to {APPROVE_MAX} approve, up to {CHALLENGE_MAX.toFixed(2)} challenge,
        above that decline.
      </p>
    </div>
  );
}
