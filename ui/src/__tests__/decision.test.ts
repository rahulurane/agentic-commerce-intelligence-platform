import { describe, expect, it } from "vitest";
import { decisionColor, decisionLabel } from "../decision";

describe("decisionColor", () => {
  it("maps APPROVE to green (approve)", () => {
    expect(decisionColor("APPROVE")).toBe("approve");
  });

  it("maps CHALLENGE to amber (challenge)", () => {
    expect(decisionColor("CHALLENGE")).toBe("challenge");
  });

  it("maps DECLINE to red (decline)", () => {
    expect(decisionColor("DECLINE")).toBe("decline");
  });

  it("is case-insensitive", () => {
    expect(decisionColor("approve")).toBe("approve");
  });

  it("handles null / unknown gracefully", () => {
    expect(decisionColor(null)).toBe("unknown");
    expect(decisionColor(undefined)).toBe("unknown");
    expect(decisionColor("WHATEVER")).toBe("unknown");
  });
});

describe("decisionLabel", () => {
  it("falls back to Pending for unknown", () => {
    expect(decisionLabel(null)).toBe("Pending");
    expect(decisionLabel("APPROVE")).toBe("APPROVE");
  });
});
