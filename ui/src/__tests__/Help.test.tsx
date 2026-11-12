import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";

function stubIdleFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => ({ items: [], status: "ok" }),
    })),
  );
}

describe("Help drawer", () => {
  it("opens from the button, traps focus, closes on Esc and restores focus", async () => {
    stubIdleFetch();
    const user = userEvent.setup();
    render(<App />);
    const trigger = screen.getByRole("button", { name: /^help/i });
    await user.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: /help guide/i });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const close = screen.getByRole("button", { name: /close help/i });
    await waitFor(() => expect(close).toHaveFocus());
    expect(document.querySelector(".app")).toHaveAttribute("inert");
    for (let i = 0; i < 40; i++) {
      await user.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
    expect(screen.getAllByRole("link", { name: /glossary/i })[0]).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
    expect(document.querySelector(".app")).not.toHaveAttribute("inert");
  });

  it("opens with ? and closes via the backdrop and close button", async () => {
    stubIdleFetch();
    const user = userEvent.setup();
    render(<App />);
    await user.keyboard("?");
    await screen.findByRole("dialog", { name: /help guide/i });
    await user.click(screen.getByTestId("help-backdrop"));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await user.keyboard("?");
    await screen.findByRole("dialog", { name: /help guide/i });
    await user.click(screen.getByRole("button", { name: /close help/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("ignores ? typed into a form field", async () => {
    stubIdleFetch();
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /custom checkout/i }));
    const field = screen.getAllByRole("textbox")[0];
    await user.click(field);
    await user.keyboard("?");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("marks the current section with aria-current", async () => {
    stubIdleFetch();
    const user = userEvent.setup();
    render(<App />);
    await user.keyboard("?");
    await screen.findByRole("dialog");
    const link = screen.getByRole("link", { name: "Troubleshooting" });
    await user.click(link);
    expect(link).toHaveAttribute("aria-current", "true");
  });
});

describe("Guided tour", () => {
  it("auto-starts when unset, walks 6 steps, completes and persists", async () => {
    stubIdleFetch();
    window.localStorage.removeItem("acip.tour.done");
    const user = userEvent.setup();
    render(<App />);
    const tour = await screen.findByRole("dialog", { name: /guided tour/i }, { timeout: 2000 });
    expect(tour).toHaveTextContent("Step 1 of 6");
    for (let i = 2; i <= 6; i++) {
      await user.click(screen.getByRole("button", { name: "Next" }));
      expect(screen.getByRole("dialog", { name: /guided tour/i })).toHaveTextContent(
        `Step ${i} of 6`,
      );
    }
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("dialog", { name: /guided tour/i })).toHaveTextContent("Step 5 of 6");
    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByRole("dialog", { name: /guided tour/i })).not.toBeInTheDocument();
    expect(window.localStorage.getItem("acip.tour.done")).toBe("1");
  });

  it("can be skipped with Esc and is remembered", async () => {
    stubIdleFetch();
    window.localStorage.removeItem("acip.tour.done");
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("dialog", { name: /guided tour/i }, { timeout: 2000 });
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: /guided tour/i })).not.toBeInTheDocument();
    expect(window.localStorage.getItem("acip.tour.done")).toBe("1");
  });

  it("does not auto-start when done, and replays from the header, empty state and help", async () => {
    stubIdleFetch();
    const user = userEvent.setup();
    render(<App />);
    expect(screen.queryByRole("dialog", { name: /guided tour/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^tour$/i }));
    expect(screen.getByRole("dialog", { name: /guided tour/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Skip tour" }));
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    expect(screen.getByRole("dialog", { name: /guided tour/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Skip tour" }));
    await user.click(screen.getByRole("button", { name: "Open help guide" }));
    await screen.findByRole("dialog", { name: /help guide/i });
    await user.click(screen.getByRole("button", { name: /replay tour/i }));
    expect(screen.getByRole("dialog", { name: /guided tour/i })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: /help guide/i })).not.toBeInTheDocument();
  });
});
