import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TestsPage } from "./TestsPage";

vi.mock("../lib/api", () => ({
  fetchTests: vi.fn(),
}));

import { fetchTests } from "../lib/api";

describe("TestsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state and then status cards after refresh", async () => {
    vi.mocked(fetchTests)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          status: "failed",
          summary: "回归检查",
          command: "pnpm test",
          failure_info: "snapshot mismatch",
        },
      ] as any);
    const user = userEvent.setup();
    render(<TestsPage />);
    expect(await screen.findByText("暂无测试记录")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "刷新" }));
    expect(await screen.findByText("回归检查")).toBeInTheDocument();
    expect(screen.getByText("pnpm test")).toBeInTheDocument();
    expect(screen.getByText("snapshot mismatch")).toBeInTheDocument();
  });

  it("surfaces load error", async () => {
    vi.mocked(fetchTests).mockRejectedValue(new Error("tests down"));
    render(<TestsPage />);
    await waitFor(() => {
      expect(screen.getByText("tests down")).toBeInTheDocument();
    });
  });
});
