import { useEffect, type RefObject } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Keep Tab focus inside `ref` while `active`, move focus in on activation, and return it
 * to the previously focused element (the trigger) on deactivation.
 */
export function useFocusTrap(ref: RefObject<HTMLElement>, active: boolean): void {
  useEffect(() => {
    const root = ref.current;
    if (!active || !root) {
      return;
    }
    const previous = document.activeElement as HTMLElement | null;
    const items = () => Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE));
    items()[0]?.focus();

    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Tab") {
        return;
      }
      const list = items();
      if (list.length === 0) {
        e.preventDefault();
        return;
      }
      const first = list[0];
      const last = list[list.length - 1];
      const current = document.activeElement;
      if (e.shiftKey && (current === first || !root!.contains(current))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (current === last || !root!.contains(current))) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previous?.focus?.();
    };
  }, [ref, active]);
}
