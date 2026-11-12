// localStorage wrapper that never throws (storage can be blocked, full or corrupt).
export const THEME_KEY = "acip.theme";
export const TOUR_DONE_KEY = "acip.tour.done";

export function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStorage(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable: the preference simply does not persist.
  }
}
