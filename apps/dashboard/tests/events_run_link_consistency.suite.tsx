import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("../lib/api", () => ({
  fetchAllEvents: vi.fn(),
}));

import EventsPage from "../app/events/page";
import { fetchAllEvents } from "../lib/api";

describe("events run link consistency", () => {
  const mockFetchAllEvents = vi.mocked(fetchAllEvents);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("binds each run link to full run id with encoded href", async () => {
    mockFetchAllEvents.mockResolvedValue([
      {
        event: "RUN_UPDATED",
        _run_id: "run/alpha beta",
        ts: "2026-02-21T10:00:00Z",
      },
    ] as never[]);

    render(await EventsPage());

    const link = screen.getByRole("link", { name: "run/alpha be..." });
    expect(link).toHaveAttribute("href", "/runs/run%2Falpha%20beta");
    expect(link).toHaveAttribute("title", "run/alpha beta");
    expect(link).toHaveAttribute("data-run-id", "run/alpha beta");
  });
});
