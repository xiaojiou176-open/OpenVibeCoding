import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { UI_LOCALE_STORAGE_KEY } from "@openvibecoding/frontend-shared/uiLocale";

const { mockRefresh, mockPathname } = vi.hoisted(() => ({
  mockRefresh: vi.fn(),
  mockPathname: vi.fn(() => "/"),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    refresh: mockRefresh,
  }),
  usePathname: () => mockPathname(),
}));

vi.mock("../components/AppNav", () => ({
  default: ({ locale, compact }: { locale: "en" | "zh-CN"; compact?: boolean }) => (
    <nav
      aria-label={locale === "zh-CN" ? "控制台导航" : "Dashboard navigation"}
      data-compact={compact ? "true" : "false"}
      data-testid="app-nav"
    >
      {locale === "zh-CN" ? "控制台导航" : "Dashboard navigation"}
    </nav>
  ),
}));

import DashboardShellChrome from "../components/DashboardShellChrome";

function clearLocaleCookie() {
  document.cookie = `${UI_LOCALE_STORAGE_KEY}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
}

describe("DashboardShellChrome", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPathname.mockReturnValue("/");
    clearLocaleCookie();
    window.localStorage.clear();
  });

  it("renders landing chrome with compact nav and landing brand", () => {
    render(
      <DashboardShellChrome>
        <div>content</div>
      </DashboardShellChrome>,
    );

    expect(screen.getByRole("link", { name: "OpenVibeCoding" })).toHaveTextContent("OVC");
    expect(screen.getByTestId("app-nav")).toHaveAttribute("data-compact", "true");
    expect(screen.queryByText("Governance view")).not.toBeInTheDocument();
    expect(screen.queryByText("Live verification required")).not.toBeInTheDocument();
    expect(screen.queryByText("Page-level status")).not.toBeInTheDocument();
  });

  it("renders non-landing chrome with live badges and full brand", () => {
    mockPathname.mockReturnValue("/command-tower");

    render(
      <DashboardShellChrome>
        <div>content</div>
      </DashboardShellChrome>,
    );

    expect(screen.getByRole("link", { name: "OpenVibeCoding" })).toHaveTextContent("OpenVibeCoding");
    expect(screen.getByTestId("app-nav")).toHaveAttribute("data-compact", "false");
    expect(screen.getByText("Live operator shell")).toBeInTheDocument();
    expect(screen.getByText("Operator shell")).toBeInTheDocument();
    expect(screen.getByText("Live read-back")).toBeInTheDocument();
    expect(screen.getByText("Page contract")).toBeInTheDocument();
  });

  it("adopts stored zh-CN locale from browser state and refreshes once", async () => {
    mockPathname.mockReturnValue("/command-tower");
    window.localStorage.setItem(UI_LOCALE_STORAGE_KEY, "zh-CN");

    render(
      <DashboardShellChrome>
        <div>content</div>
      </DashboardShellChrome>,
    );

    await waitFor(() => expect(screen.getByText("实时操作壳层")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "切换到英文" })).toBeInTheDocument();
    expect(mockRefresh).toHaveBeenCalled();
  });

  it("keeps explicit server locale when it already differs from the default", async () => {
    mockPathname.mockReturnValue("/command-tower");
    window.localStorage.setItem(UI_LOCALE_STORAGE_KEY, "en");

    render(
      <DashboardShellChrome initialLocale="zh-CN">
        <div>content</div>
      </DashboardShellChrome>,
    );

    await waitFor(() => expect(screen.getByText("实时操作壳层")).toBeInTheDocument());
    expect(mockRefresh).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(UI_LOCALE_STORAGE_KEY)).toBe("zh-CN");
  });

  it("toggles locale and persists the new preference", async () => {
    mockPathname.mockReturnValue("/command-tower");

    render(
      <DashboardShellChrome>
        <div>content</div>
      </DashboardShellChrome>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Switch to Chinese" }));

    await waitFor(() => expect(screen.getByText("实时操作壳层")).toBeInTheDocument());
    expect(window.localStorage.getItem(UI_LOCALE_STORAGE_KEY)).toBe("zh-CN");
    expect(mockRefresh).toHaveBeenCalled();
  });
});
