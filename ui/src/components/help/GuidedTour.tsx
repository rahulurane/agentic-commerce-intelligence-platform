import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { TOUR_STEPS } from "../../content/tour";

interface Props {
  /** Called on completion or skip. */
  onClose: () => void;
}

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

const PAD = 6;
const POP_WIDTH = 340;

function findTarget(name: string): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[data-tour="${name}"]`);
}

/** Hand-rolled coachmark tour: spotlight + popover, centred when the target is missing. */
export default function GuidedTour({ onClose }: Props) {
  const [index, setIndex] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const step = TOUR_STEPS[index];
  const last = index === TOUR_STEPS.length - 1;

  const measure = useCallback(() => {
    const el = findTarget(step.target);
    if (!el) {
      setBox(null);
      return;
    }
    const r = el.getBoundingClientRect();
    setBox({ top: r.top, left: r.left, width: r.width, height: r.height });
  }, [step.target]);

  useLayoutEffect(() => {
    findTarget(step.target)?.scrollIntoView({ block: "center", behavior: "auto" });
    measure();
  }, [step.target, measure]);

  useEffect(() => {
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [measure]);

  useEffect(() => {
    nextRef.current?.focus();
  }, [index]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  let style: React.CSSProperties = {};
  if (box) {
    const below = box.top + box.height + PAD + 12;
    const fitsBelow = below + 200 < window.innerHeight;
    const left = Math.max(12, Math.min(box.left, window.innerWidth - POP_WIDTH - 12));
    style = fitsBelow
      ? { top: below, left }
      : { top: Math.max(12, box.top - PAD - 12 - 200), left };
  }

  return (
    <div className="tour" data-testid="tour">
      {box ? (
        <div
          className="tour__spot"
          style={{
            top: box.top - PAD,
            left: box.left - PAD,
            width: box.width + PAD * 2,
            height: box.height + PAD * 2,
          }}
        />
      ) : (
        <div className="tour__dim" />
      )}
      <div
        className={`tour__pop${box ? "" : " tour__pop--center"}`}
        style={style}
        role="dialog"
        aria-label="Guided tour"
        aria-describedby="tour-text"
      >
        <p className="tour__step">
          Step {index + 1} of {TOUR_STEPS.length}
        </p>
        <p id="tour-text" className="tour__text">
          {step.text}
        </p>
        <div className="tour__actions">
          <button type="button" className="btn btn--ghost btn--sm" onClick={onClose}>
            Skip tour
          </button>
          <span className="tour__spacer" />
          {index > 0 && (
            <button type="button" className="btn btn--sm" onClick={() => setIndex(index - 1)}>
              Back
            </button>
          )}
          <button
            ref={nextRef}
            type="button"
            className="btn btn--primary btn--sm"
            onClick={() => (last ? onClose() : setIndex(index + 1))}
          >
            {last ? "Done" : "Next"}
          </button>
        </div>
      </div>
    </div>
  );
}
