import { useEffect, useState } from "react";
import { copyText } from "../../lib/clipboard";
import Icon from "./Icon";

interface Props {
  text: string;
  /** What is being copied, e.g. "transaction ID". */
  what: string;
}

/** Copy-to-clipboard button with a polite live announcement. */
export default function CopyButton({ text, what }: Props) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) {
      return;
    }
    const t = setTimeout(() => setCopied(false), 1800);
    return () => clearTimeout(t);
  }, [copied]);

  async function handleClick() {
    if (await copyText(text)) {
      setCopied(true);
    }
  }

  return (
    <span className="copy">
      <button
        type="button"
        className="btn btn--ghost btn--icon btn--sm"
        aria-label={`Copy ${what}`}
        onClick={() => void handleClick()}
      >
        <Icon name={copied ? "check-circle" : "copy"} size={16} />
      </button>
      <span className="sr-only" aria-live="polite">
        {copied ? "Copied" : ""}
      </span>
    </span>
  );
}
