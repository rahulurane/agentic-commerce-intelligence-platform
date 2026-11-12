import { useEffect, useRef, useState } from "react";
import { useFocusTrap } from "../../lib/useFocusTrap";
import { GLOSSARY } from "../../content/glossary";
import {
  HELP_SECTIONS,
  OUTCOME_HELP,
  SCENARIO_GUIDE,
  TROUBLESHOOTING,
  type HelpSection,
} from "../../content/help";
import { STAGE_CONTENT } from "../../content/stages";
import { AGENTS } from "../../domain/agents";
import Icon from "../ui/Icon";

interface Props {
  onClose: () => void;
  onReplayTour: () => void;
}

function SectionBody({ section }: { section: HelpSection }) {
  switch (section.kind) {
    case "stages":
      return (
        <ol className="help__list">
          {STAGE_CONTENT.map((s) => (
            <li key={s.id}>
              <strong>{s.title}.</strong> {s.how}
            </li>
          ))}
        </ol>
      );
    case "agents":
      return (
        <ul className="help__cards">
          {AGENTS.map((a) => (
            <li key={a.key} className="help__card">
              <h4>
                <Icon name={a.icon} size={18} /> {a.name}
              </h4>
              <p>{a.role}</p>
              <p className="muted">Looks at: {a.looksAt}</p>
              <p>
                {a.badges.map((b) => (
                  <span key={b} className="badge">
                    {b}
                  </span>
                ))}
              </p>
            </li>
          ))}
        </ul>
      );
    case "outcomes":
      return (
        <dl className="help__dl">
          {OUTCOME_HELP.map((o) => (
            <div key={o.name}>
              <dt>{o.name}</dt>
              <dd>{o.text}</dd>
            </div>
          ))}
        </dl>
      );
    case "scenarios":
      return (
        <>
          <p className="muted">What each scenario is set up to show</p>
          <dl className="help__dl">
            {SCENARIO_GUIDE.map((s) => (
              <div key={s.name}>
                <dt>{s.name}</dt>
                <dd>{s.text}</dd>
              </div>
            ))}
          </dl>
        </>
      );
    case "glossary":
      return (
        <dl className="help__dl">
          {GLOSSARY.map((g) => (
            <div key={g.term}>
              <dt>{g.term}</dt>
              <dd>{g.text}</dd>
            </div>
          ))}
        </dl>
      );
    case "faq":
      return (
        <dl className="help__dl">
          {TROUBLESHOOTING.map((t) => (
            <div key={t.q}>
              <dt>{t.q}</dt>
              <dd>{t.a}</dd>
            </div>
          ))}
        </dl>
      );
    default:
      return null;
  }
}

/** Slide-over help guide. Loaded lazily so the help copy is a separate chunk. */
export default function HelpDrawer({ onClose, onReplayTour }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(HELP_SECTIONS[0].id);
  useFocusTrap(panelRef, true);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape") {
        return;
      }
      // An open InfoTip inside the drawer closes first.
      const el = document.activeElement;
      if (el instanceof HTMLElement && el.closest(".infotip") && el.ariaExpanded === "true") {
        return;
      }
      onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  function go(id: string) {
    setActive(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="help-backdrop" onClick={onClose} data-testid="help-backdrop">
      <div
        ref={panelRef}
        className="help"
        role="dialog"
        aria-modal="true"
        aria-labelledby="help-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="help__head">
          <h2 id="help-title">Help guide</h2>
          <button
            type="button"
            className="btn btn--ghost btn--icon help__close"
            onClick={onClose}
            aria-label="Close help"
          >
            <Icon name="x-circle" />
          </button>
          <button type="button" className="btn btn--sm" onClick={onReplayTour}>
            <Icon name="play" size={16} /> Replay tour
          </button>
        </div>
        <div className="help__body">
          <nav className="help__nav" aria-label="Help sections">
            <ul>
              {HELP_SECTIONS.map((s) => (
                <li key={s.id}>
                  <a
                    href={`#${s.id}`}
                    aria-current={active === s.id ? "true" : undefined}
                    onClick={(e) => {
                      e.preventDefault();
                      go(s.id);
                    }}
                  >
                    {s.title}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <div className="help__content" tabIndex={0} role="region" aria-label="Help content">
            {HELP_SECTIONS.map((s) => (
              <section key={s.id} id={s.id} aria-labelledby={`${s.id}-h`} className="help__section">
                <h3 id={`${s.id}-h`}>{s.title}</h3>
                {s.kind !== "stages" && s.paragraphs?.map((p) => <p key={p}>{p}</p>)}
                <SectionBody section={s} />
                {s.kind === "stages" && s.paragraphs?.map((p) => <p key={p}>{p}</p>)}
              </section>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
