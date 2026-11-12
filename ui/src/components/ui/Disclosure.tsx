import { useId, useState, type ReactNode } from "react";
import Icon from "./Icon";

interface Props {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

/** Button-controlled collapsible region (aria-expanded + aria-controls). */
export default function Disclosure({ title, defaultOpen = false, children }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const regionId = useId();
  return (
    <div className="disclosure">
      <button
        type="button"
        className="disclosure__btn"
        aria-expanded={open}
        aria-controls={regionId}
        onClick={() => setOpen((v) => !v)}
      >
        <span>{title}</span>
        <Icon name="chevron" className="disclosure__chev" />
      </button>
      <div
        id={regionId}
        role="region"
        aria-label={title}
        className="disclosure__body"
        hidden={!open}
      >
        {children}
      </div>
    </div>
  );
}
