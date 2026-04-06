import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Card, CardContent, CardFooter, CardHeader } from "../components/ui/card";

describe("dashboard ui card primitives", () => {
  it("renders the default card class and keeps custom classes", () => {
    render(
      <Card className="custom-card" data-testid="card-root">
        content
      </Card>,
    );

    expect(screen.getByTestId("card-root")).toHaveClass("ui-card");
    expect(screen.getByTestId("card-root")).toHaveClass("card");
    expect(screen.getByTestId("card-root")).toHaveClass("custom-card");
  });

  it("supports shadcn-style card slots", () => {
    render(
      <Card>
        <CardHeader data-testid="card-header">Header</CardHeader>
        <CardContent data-testid="card-content">Body</CardContent>
        <CardFooter data-testid="card-footer">Footer</CardFooter>
      </Card>,
    );

    expect(screen.getByTestId("card-header")).toHaveClass("ui-card__header");
    expect(screen.getByTestId("card-header")).toHaveClass("card-header");
    expect(screen.getByTestId("card-content")).toHaveClass("ui-card__content");
    expect(screen.getByTestId("card-content")).toHaveClass("card-body");
    expect(screen.getByTestId("card-footer")).toHaveClass("ui-card__footer");
    expect(screen.getByTestId("card-footer")).toHaveClass("card-footer");
  });

  it("applies variant classes, including unstyled", () => {
    const { rerender } = render(
      <Card variant="table" data-testid="variant-card">
        table
      </Card>,
    );

    expect(screen.getByTestId("variant-card")).toHaveClass("ui-card");
    expect(screen.getByTestId("variant-card")).toHaveClass("ui-card--table");
    expect(screen.getByTestId("variant-card")).toHaveClass("card");
    expect(screen.getByTestId("variant-card")).toHaveClass("table-card");

    rerender(
      <Card variant="unstyled" className="plain-shell" data-testid="variant-card">
        plain
      </Card>,
    );

    expect(screen.getByTestId("variant-card")).toHaveClass("plain-shell");
    expect(screen.getByTestId("variant-card")).not.toHaveClass("card");
  });

  it("supports asChild composition for linked card shells", () => {
    render(
      <Card asChild variant="compact">
        <a href="/runs/test" data-testid="card-link">
          linked
        </a>
      </Card>,
    );

    expect(screen.getByTestId("card-link")).toHaveAttribute("href", "/runs/test");
    expect(screen.getByTestId("card-link")).toHaveClass("ui-card");
    expect(screen.getByTestId("card-link")).toHaveClass("ui-card--compact");
    expect(screen.getByTestId("card-link")).toHaveClass("card");
    expect(screen.getByTestId("card-link")).toHaveClass("compact-status-card");
  });
});
