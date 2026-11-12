import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ThemeProvider from "../theme/ThemeProvider";
import ThemeToggle from "../components/layout/ThemeToggle";

function mount() {
  return render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  );
}

describe("theme", () => {
  it("is light by default, even when the OS prefers dark", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn((query: string) => ({
        matches: true,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    mount();
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("toggles to dark, persists, and restores on remount", async () => {
    const user = userEvent.setup();
    const first = mount();
    await user.click(screen.getByRole("button", { name: /switch to dark theme/i }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(window.localStorage.getItem("acip.theme")).toBe("dark");
    first.unmount();
    mount();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(screen.getByRole("button", { name: /switch to light theme/i })).toBeInTheDocument();
  });

  it("does not throw when storage is unavailable", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const user = userEvent.setup();
    mount();
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    await user.click(screen.getByRole("button", { name: /switch to dark theme/i }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    getItem.mockRestore();
    setItem.mockRestore();
  });
});
