import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Badge } from "../components/ui/badge";
import { Button, buttonClasses } from "../components/ui/button";

describe("dashboard ui button and badge primitives", () => {
  it("defaults button type to button and supports asChild composition", () => {
    const { rerender } = render(
      <Button data-testid="primitive-button">Run</Button>,
    );

    expect(screen.getByTestId("primitive-button")).toHaveAttribute("type", "button");
    expect(screen.getByTestId("primitive-button")).toHaveClass("ui-button--secondary");

    rerender(
      <Button asChild variant="warning">
        <a href="/runs/test" data-testid="primitive-button-link">
          Linked
        </a>
      </Button>,
    );

    expect(screen.getByTestId("primitive-button-link")).toHaveAttribute("href", "/runs/test");
    expect(screen.getByTestId("primitive-button-link")).not.toHaveAttribute("type");
    expect(screen.getByTestId("primitive-button-link")).toHaveClass("ui-button--warning");
  });

  it("covers unstyled class helpers for button and badge", () => {
    render(
      <>
        <Button variant="unstyled" className="plain-button" data-testid="unstyled-button">
          Plain
        </Button>
        <Badge variant="unstyled" className="plain-badge" data-testid="unstyled-badge">
          Quiet
        </Badge>
      </>,
    );

    expect(buttonClasses("unstyled", "plain-inline")).toBe("plain-inline");
    expect(screen.getByTestId("unstyled-button")).toHaveClass("plain-button");
    expect(screen.getByTestId("unstyled-button")).not.toHaveAttribute("data-ui-primitive");
    expect(screen.getByTestId("unstyled-badge")).toHaveClass("plain-badge");
    expect(screen.getByTestId("unstyled-badge")).not.toHaveAttribute("data-ui-primitive");
  });
});
