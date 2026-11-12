import { agentInfo } from "../../domain/agents";
import type { RunResult } from "../../domain/journey";
import Icon from "../ui/Icon";

interface Props {
  result: RunResult;
}

/** Plain-English reason, derived only from returned data, with the engine's own words verbatim. */
export default function WhyPanel({ result }: Props) {
  const { why, explanation } = result;
  const drivers = why.drivers.map((k) => agentInfo(k)?.name ?? k);
  return (
    <section className="card why" aria-labelledby="why-title">
      <div className="card__head">
        <h2 id="why-title">Why this decision</h2>
      </div>
      <p className="why__headline">
        <Icon name="help" size={20} />
        {why.headline}
      </p>
      {why.body && <p className="why__body">{why.body}</p>}
      {explanation && (
        <blockquote className="why__quote">
          <span className="why__quote-label">Decision engine said:</span> {explanation}
        </blockquote>
      )}
      {why.factors.length > 0 && (
        <ul className="why__factors" aria-label="Factors">
          {why.factors.map((f) => (
            <li key={f} className="badge tone-neutral">
              {f}
            </li>
          ))}
        </ul>
      )}
      {drivers.length > 0 && (
        <p className="why__drivers">
          Agents that drove this outcome: <strong>{drivers.join(", ")}</strong>
        </p>
      )}
    </section>
  );
}
