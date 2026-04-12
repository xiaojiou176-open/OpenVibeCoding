import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EventsPage } from "./EventsPage";

vi.mock("../lib/api", () => ({
  fetchAllEvents: vi.fn(),
}));

import { fetchAllEvents } from "../lib/api";

describe("EventsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("toggles row details by click", async () => {
    vi.mocked(fetchAllEvents).mockResolvedValueOnce([
      {
        ts: new Date("2026-01-01T00:00:00Z").toISOString(),
        event: "TEST_EVENT",
        level: "INFO",
        task_id: "task-001",
        run_id: "run-001",
        context: { detail: "ok" },
      },
    ] as any);

    const user = userEvent.setup();
    render(<EventsPage />);

    const rowToggle = await screen.findByRole("button", { name: "View event details TEST_EVENT" });
    expect(rowToggle).toHaveAttribute("aria-expanded", "false");

    await user.click(rowToggle);
    expect(rowToggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText((text) => text.includes('"detail": "ok"'))).toBeInTheDocument();

    await user.click(rowToggle);
    expect(rowToggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText((text) => text.includes('"detail": "ok"'))).not.toBeInTheDocument();
  });

  it("supports keyboard toggle on semantic button", async () => {
    vi.mocked(fetchAllEvents).mockResolvedValueOnce([
      {
        ts: new Date("2026-01-01T00:00:00Z").toISOString(),
        event: "KEYBOARD_EVENT",
        level: "INFO",
        task_id: "task-002",
        run_id: "run-002",
        context: { detail: "keyboard" },
      },
    ] as any);

    const user = userEvent.setup();
    render(<EventsPage />);

    const rowToggle = await screen.findByRole("button", { name: "View event details KEYBOARD_EVENT" });
    rowToggle.focus();
    await user.keyboard("{Enter}");
    expect(rowToggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText((text) => text.includes('"detail": "keyboard"'))).toBeInTheDocument();
  });
});
