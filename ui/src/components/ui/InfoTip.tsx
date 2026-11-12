import { useEffect, useId, useState } from "react";
import Icon from "./Icon";

interface Props {
  /** The term being explained; used for the accessible name. */
  term: string;
  /** Explanation shown in the popover. */
  text: string;
}

/** Small (i) button whose popover opens on hover, focus or click and closes on Esc/blur. */
export default function InfoTip({ term, text }: Props) {
  const id = useId();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <span
      className="infotip"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="infotip__btn"
        aria-label={`About ${term}`}
        aria-describedby={id}
        aria-expanded={open}
        onClick={() => setOpen(true)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        <Icon name="info" size={16} />
      </button>
      <span id={id} role="tooltip" className="infotip__pop" hidden={!open}>
        {text}
      </span>
    </span>
  );
}
