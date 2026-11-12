// Loads the jest-dom matchers (toBeInTheDocument, etc.) for every Vitest test and gives
// each test a clean browser environment.
import "@testing-library/jest-dom";
import { beforeEach, vi } from "vitest";

beforeEach(() => {
  window.localStorage.clear();
  // Tests start with the guided tour already completed so it never auto-opens.
  window.localStorage.setItem("acip.tour.done", "1");
  document.documentElement.removeAttribute("data-theme");
  // jsdom has no matchMedia: default to "nothing matches" (light, motion allowed).
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
  Element.prototype.scrollIntoView = vi.fn();
});
