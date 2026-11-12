import { useId, type ReactNode } from "react";
import { TOOLTIPS } from "../../content/tooltips";
import { STAGE_STATUS_LABEL, type StageModel } from "../../domain/journey";
import Icon from "../ui/Icon";
import InfoTip from "../ui/InfoTip";

interface Props {
  model: StageModel;
  open: boolean;
  onToggle: () => void;
  children?: ReactNode;
}

/** One journey stage: an accessible disclosure with summary, what happened and how it works. */
export default function JourneyStage({ model, open, onToggle, children }: Props) {
  const { content, status } = model;
  const bodyId = useId();
  const queued = status === "queued";
  const showBody = open && !queued;

  return (
    <li className={`stage stage--${status}`} aria-busy={status === "evaluating"}>
      <h3 className="stage__heading">
        <button
          type="button"
          className="stage__btn"
          aria-expanded={showBody}
          aria-controls={bodyId}
          disabled={queued}
          onClick={onToggle}
        >
          <span className="stage__num" aria-hidden="true">
            {content.id}
          </span>
          <Icon name={content.icon} size={20} className="stage__icon" />
          <span className="stage__text">
            <span className="stage__title">{content.title}</span>
            <span className="stage__summary">{content.summary}</span>
          </span>
          <span className={`stage__status stage__status--${status}`}>
            {status === "evaluating" && <span className="spinner" aria-hidden="true" />}
            {status === "done" && <Icon name="check-circle" size={14} />}
            {status === "error" && <Icon name="x-circle" size={14} />}
            {(status === "checking" || status === "unconfirmed") && (
              <Icon name="alert-triangle" size={14} />
            )}
            {STAGE_STATUS_LABEL[status]}
          </span>
          <Icon name="chevron" size={18} className="stage__chev" />
        </button>
      </h3>
      <div id={bodyId} className="stage__body" hidden={!showBody}>
        {model.happened.length > 0 && (
          <div className="stage__happened">
            <h4>What happened</h4>
            {model.happened.map((line) => (
              <p key={line}>{line}</p>
            ))}
            {model.quote && (
              <blockquote className="stage__quote">
                <span className="stage__quote-label">Decision engine said:</span> {model.quote}
              </blockquote>
            )}
            {model.notes.map((note) => (
              <p key={note} className="stage__note">
                {note}
              </p>
            ))}
          </div>
        )}
        <div className="stage__how">
          <h4>How it works</h4>
          <p>{content.how}</p>
          {content.terms.length > 0 && (
            <p className="stage__terms">
              {content.terms.map((t) => (
                <span key={t.key} className="stage__term">
                  {t.label}
                  <InfoTip term={t.label} text={TOOLTIPS[t.key]} />
                </span>
              ))}
            </p>
          )}
        </div>
        {children}
      </div>
    </li>
  );
}
