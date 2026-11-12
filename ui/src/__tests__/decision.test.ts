import { describe, expect, it } from "vitest";
import { decisionColor, decisionIcon, decisionLabel, decisionTone } from "../decision";

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

describe("decisionIcon / decisionTone", () => {
  it("pairs every decision with an icon and a tone so colour is never the only signal", () => {
    expect(decisionIcon("APPROVE")).toBe("check-circle");
    expect(decisionIcon("CHALLENGE")).toBe("alert-triangle");
    expect(decisionIcon("DECLINE")).toBe("x-circle");
    expect(decisionIcon("nope")).toBe("info");
    expect(decisionTone("APPROVE")).toBe("success");
    expect(decisionTone("CHALLENGE")).toBe("warning");
    expect(decisionTone("DECLINE")).toBe("danger");
    expect(decisionTone(null)).toBe("neutral");
  });
});
