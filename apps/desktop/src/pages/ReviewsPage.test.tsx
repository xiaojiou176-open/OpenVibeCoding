import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReviewsPage } from "./ReviewsPage";

vi.mock("../lib/api", () => ({
  fetchReviews: vi.fn(),
}));

import { fetchReviews } from "../lib/api";

describe("ReviewsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state and refreshes into populated records", async () => {
    type FirstReviewsPayload = Awaited<ReturnType<typeof fetchReviews>>;
    let resolveFirstFetch: (value: FirstReviewsPayload) => void = () => {};
    vi.mocked(fetchReviews)
      .mockImplementationOnce(
        () => new Promise<FirstReviewsPayload>((resolve) => { resolveFirstFetch = resolve; }) as any,
      )
      .mockResolvedValueOnce([
        {
          run_id: "run-1",
          verdict: "pass",
          summary: "looks good",
          scope_check: "ok",
          evidence: ["e1"],
        },
    ] as any);
    const user = userEvent.setup();
    render(<ReviewsPage />);
    expect(screen.getByRole("button", { name: "Refreshing..." })).toBeDisabled();
    resolveFirstFetch([]);
    expect(await screen.findByText("No review records yet")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText("run-1")).toBeInTheDocument();
    expect(screen.getByText("looks good")).toBeInTheDocument();
    expect(screen.getByText("Scope: ok")).toBeInTheDocument();
    expect(screen.getByText("e1")).toBeInTheDocument();
  });

  it("surfaces fetch error", async () => {
    vi.mocked(fetchReviews).mockRejectedValue(new Error("reviews down"));
    render(<ReviewsPage />);
    await waitFor(() => {
      const errorBanner = screen.getByRole("alert");
      expect(errorBanner).toHaveAttribute("aria-live", "assertive");
      expect(errorBanner).toHaveTextContent("reviews down");
    });
  });
});
