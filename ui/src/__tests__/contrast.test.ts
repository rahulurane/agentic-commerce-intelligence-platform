import { describe, expect, it } from "vitest";
import { CONTRAST_PAIRS } from "../styles/contrast-pairs";

function channel(v: number): number {
  const c = v / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const n = Number.parseInt(hex.slice(1), 16);
  return (
    0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255)
  );
}

function ratio(fg: string, bg: string): number {
  const [a, b] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

describe("WCAG AA contrast", () => {
  for (const pair of CONTRAST_PAIRS) {
    it(`${pair.name} (${pair.fg} on ${pair.bg}) >= ${pair.min}`, () => {
      expect(ratio(pair.fg, pair.bg)).toBeGreaterThanOrEqual(pair.min);
    });
  }
});
