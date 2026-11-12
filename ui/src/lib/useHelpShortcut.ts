import { useEffect } from "react";

const EDITABLE = "input, textarea, select, [contenteditable]";

/** Call `onHelp` when "?" is pressed outside form fields and without modifier keys. */
export function useHelpShortcut(onHelp: () => void, enabled: boolean): void {
  useEffect(() => {
    if (!enabled) {
      return;
    }
    function onKey(e: KeyboardEvent) {
      if (e.key !== "?" || e.ctrlKey || e.metaKey || e.altKey) {
        return;
      }
      const t = e.target;
      if (t instanceof Element && t.closest(EDITABLE)) {
        return;
      }
      e.preventDefault();
      onHelp();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onHelp, enabled]);
}
