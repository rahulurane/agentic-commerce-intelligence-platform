import { useEffect, useState } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

/** True when the user asked the OS/browser for reduced motion. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() =>
    typeof window.matchMedia === "function" ? window.matchMedia(QUERY).matches : false,
  );

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return;
    }
    const mql = window.matchMedia(QUERY);
    const onChange = () => setReduced(mql.matches);
    mql.addEventListener?.("change", onChange);
    return () => mql.removeEventListener?.("change", onChange);
  }, []);

  return reduced;
}
