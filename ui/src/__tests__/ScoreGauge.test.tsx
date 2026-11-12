import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ScoreGauge from "../components/journey/ScoreGauge";

describe("ScoreGauge", () => {
  it("exposes an image role with a text alternative including the score and default bands", () => {
    render(<ScoreGauge score={0.28} veto={false} />);
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("aria-label", expect.stringContaining("0.280"));
    expect(img).toHaveAttribute("aria-label", expect.stringContaining("up to 0.35 approve"));
    expect(img).toHaveAttribute("aria-label", expect.stringContaining("above that decline"));
  });

  it("is hidden and says scoring was skipped on a veto", () => {
    render(<ScoreGauge score={1} veto />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText("Scoring skipped")).toBeInTheDocument();
  });

  it("says there is no score when the API returned none", () => {
    render(<ScoreGauge score={null} veto={false} />);
    expect(screen.getByText("No score")).toBeInTheDocument();
  });
});
