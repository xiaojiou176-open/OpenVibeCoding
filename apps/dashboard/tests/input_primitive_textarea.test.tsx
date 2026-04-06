import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Input, Select, Textarea } from "../components/ui/input";

describe("dashboard ui input primitives", () => {
  it("applies default input classes and forwards input ref", () => {
    const ref = createRef<HTMLInputElement>();
    render(<Input ref={ref} className="custom-input" data-testid="dashboard-input" />);

    const input = screen.getByTestId("dashboard-input");
    expect(input).toHaveClass("ui-input");
    expect(input).toHaveClass("input");
    expect(input).toHaveClass("custom-input");
    expect(ref.current).toBe(input);
  });

  it("applies default textarea classes and forwards textarea ref", () => {
    const ref = createRef<HTMLTextAreaElement>();
    render(<Textarea ref={ref} rows={3} className="custom-textarea" data-testid="dashboard-textarea" />);

    const textarea = screen.getByTestId("dashboard-textarea");
    expect(textarea).toHaveClass("ui-input");
    expect(textarea).toHaveClass("ui-textarea");
    expect(textarea).toHaveClass("input");
    expect(textarea).toHaveClass("custom-textarea");
    expect(textarea).toHaveAttribute("rows", "3");
    expect(ref.current).toBe(textarea);
  });

  it("applies default select classes and forwards select ref", () => {
    const ref = createRef<HTMLSelectElement>();
    render(
      <Select ref={ref} className="custom-select" data-testid="dashboard-select" defaultValue="b">
        <option value="a">A</option>
        <option value="b">B</option>
      </Select>,
    );

    const select = screen.getByTestId("dashboard-select");
    expect(select).toHaveClass("ui-input");
    expect(select).toHaveClass("input");
    expect(select).toHaveClass("custom-select");
    expect(select).toHaveValue("b");
    expect(ref.current).toBe(select);
  });

  it("keeps unstyled variant without injecting input class", () => {
    render(
      <>
        <Input variant="unstyled" className="plain-input" data-testid="plain-input" />
        <Select variant="unstyled" className="plain-select" data-testid="plain-select" defaultValue="a">
          <option value="a">A</option>
        </Select>
        <Textarea variant="unstyled" className="plain-textarea" data-testid="plain-textarea" />
      </>,
    );

    expect(screen.getByTestId("plain-input")).toHaveClass("plain-input");
    expect(screen.getByTestId("plain-input")).not.toHaveClass("input");

    expect(screen.getByTestId("plain-select")).toHaveClass("plain-select");
    expect(screen.getByTestId("plain-select")).not.toHaveClass("input");

    expect(screen.getByTestId("plain-textarea")).toHaveClass("plain-textarea");
    expect(screen.getByTestId("plain-textarea")).not.toHaveClass("input");
  });
});
