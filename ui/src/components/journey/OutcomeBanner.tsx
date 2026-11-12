import { TOOLTIPS } from "../../content/tooltips";
import { decisionColor, decisionIcon, decisionLabel } from "../../decision";
import type { RunResult } from "../../domain/journey";
import { formatMs } from "../../lib/format";
import type { RunPhase } from "../../state/useCheckoutRun";
import CopyButton from "../ui/CopyButton";
import Icon from "../ui/Icon";
import InfoTip from "../ui/InfoTip";
import ScoreGauge from "./ScoreGauge";

interface Props {
  phase: RunPhase;
  loading: boolean;
  result: RunResult | null;
  roundTripMs: number | null;
}

/** The headline outcome: decision, gauge, route and the measured round trip. */
export default function OutcomeBanner({ phase, loading, result, roundTripMs }: Props) {
  if (phase === "evaluating" || loading) {
    return (
      <section
        className="outcome outcome--loading"
        aria-busy="true"
        aria-label="Outcome loading"
        data-tour="outcome"
      >
        <div className="skeleton skeleton--title" />
        <div className="skeleton" />
        <div className="skeleton skeleton--short" />
      </section>
    );
  }
  if (!result) {
    return null;
  }

  const color = decisionColor(result.decision);
  const partial = phase === "partial" || result.partial;

  return (
    <section
      className={`outcome outcome--${color}`}
      aria-labelledby="outcome-title"
      data-tour="outcome"
    >
      <div className="outcome__main">
        <div className="outcome__decision">
          <Icon name={decisionIcon(result.decision)} size={40} className="outcome__icon" />
          <div>
            <p className="outcome__eyebrow">
              Decision
              {partial && <span className="badge tone-warning outcome__partial">Partial</span>}
            </p>
            <h2 id="outcome-title" className="outcome__word">
              {decisionLabel(result.decision)}
            </h2>
            <p className="outcome__headline">{result.why.headline}</p>
          </div>
        </div>
        <dl className="outcome__facts">
          <div>
            <dt>
              Route <InfoTip term="route" text={TOOLTIPS.route} />
            </dt>
            <dd>{result.route ?? "None"}</dd>
          </div>
          {result.routeAlternatives.length > 0 && (
            <div>
              <dt>
                Failover <InfoTip term="failover" text={TOOLTIPS.failover} />
              </dt>
              <dd>{result.routeAlternatives.join(", ")}</dd>
            </div>
          )}
          {result.recommendedMethod && (
            <div>
              <dt>Suggested method</dt>
              <dd>{result.recommendedMethod}</dd>
            </div>
          )}
          {roundTripMs != null && (
            <div>
              <dt>
                Round trip <InfoTip term="round trip" text={TOOLTIPS.roundTrip} />
              </dt>
              <dd>{formatMs(roundTripMs)}</dd>
            </div>
          )}
          <div>
            <dt>Transaction</dt>
            <dd className="outcome__id">
              <code>{result.transactionId}</code>
              <CopyButton text={result.transactionId} what="transaction ID" />
            </dd>
          </div>
        </dl>
      </div>
      <div className="outcome__gauge">
        <ScoreGauge key={result.transactionId} score={result.compositeScore} veto={result.veto} />
      </div>
    </section>
  );
}
