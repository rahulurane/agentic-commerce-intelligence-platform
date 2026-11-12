import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import BrandMark from "../components/layout/BrandMark";

describe("BrandMark", () => {
  it("falls back to the text wordmark and co-brand line without a logo", () => {
    render(<BrandMark logoUrl={null} />);
    expect(screen.getByText("ACIP")).toBeInTheDocument();
    expect(screen.getByText(/Global Payments/)).toBeInTheDocument();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("renders the logo image when a URL is supplied", () => {
    render(<BrandMark logoUrl="/logo.svg" />);
    const img = screen.getByAltText("Global Payments");
    expect(img).toHaveAttribute("src", "/logo.svg");
    expect(screen.getByText("ACIP")).toBeInTheDocument();
  });
});
