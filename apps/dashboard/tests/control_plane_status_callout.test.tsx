import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import ControlPlaneStatusCallout from "../components/control-plane/ControlPlaneStatusCallout";

describe("ControlPlaneStatusCallout", () => {
  it.each([
    { tone: "success", expectedVariant: "success" },
    { tone: "warning", expectedVariant: "warning" },
    { tone: "failed", expectedVariant: "failed" },
    { tone: "running", expectedVariant: "running" },
    { tone: "default", expectedVariant: "default" },
  ] as const)("maps tone $tone to badge variant", ({ tone, expectedVariant }) => {
    render(
      <ControlPlaneStatusCallout
        title={`${tone} title`}
        summary="summary"
        nextAction="next"
        tone={tone}
        badgeLabel={`${tone} badge`}
      />,
    );

    expect(screen.getByText(`${tone} badge`)).toHaveAttribute("data-ui-variant", expectedVariant);
  });

  it("uses alert role and danger styling for failed tone", () => {
    render(
      <ControlPlaneStatusCallout
        title="failed title"
        summary="summary"
        nextAction="next"
        tone="failed"
        badgeLabel="failed badge"
        actions={[{ href: "/runs", label: "Open runs" }]}
      />,
    );

    const callout = screen.getByRole("alert");
    expect(callout).toHaveClass("alert", "alert-danger");
    expect(screen.getByRole("link", { name: "Open runs" })).toHaveAttribute("href", "/runs");
    expect(screen.getByText("Next step: next")).toBeInTheDocument();
  });

  it("uses warning styling without rendering optional badge or actions", () => {
    render(
      <ControlPlaneStatusCallout
        title="warning title"
        summary="summary"
        nextAction="triage the warning"
        nextStepLabel="Operator next step"
        tone="warning"
      />,
    );

    const callout = screen.getByRole("status");
    expect(callout).toHaveClass("alert", "alert-warning");
    expect(screen.getByText("Operator next step: triage the warning")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByText(/badge$/)).not.toBeInTheDocument();
  });
});
