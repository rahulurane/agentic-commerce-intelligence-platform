import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import InfoTip from "../components/ui/InfoTip";

describe("InfoTip", () => {
  it("shows on keyboard focus, wires aria-describedby, and hides on Esc", async () => {
    const user = userEvent.setup();
    render(<InfoTip term="veto" text="Ends the evaluation immediately." />);
    const button = screen.getByRole("button", { name: /about veto/i });
    const tip = screen.getByRole("tooltip", { hidden: true });
    expect(button).toHaveAttribute("aria-describedby", tip.id);
    expect(tip).not.toBeVisible();
    await user.tab();
    expect(button).toHaveFocus();
    expect(tip).toBeVisible();
    expect(tip).toHaveTextContent("Ends the evaluation immediately.");
    await user.keyboard("{Escape}");
    expect(tip).not.toBeVisible();
  });

  it("toggles on click", async () => {
    const user = userEvent.setup();
    render(<InfoTip term="route" text="The chosen processor." />);
    await user.click(screen.getByRole("button", { name: /about route/i }));
    expect(screen.getByRole("tooltip")).toBeVisible();
  });
});
