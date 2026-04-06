import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Input, Select, Textarea } from "./Input";

describe("desktop input primitives", () => {
  it("injects default ui-input class when absent and keeps custom class", () => {
    const ref = createRef<HTMLInputElement>();
    render(<Input ref={ref} className="composer" data-testid="desktop-input" />);

    const input = screen.getByTestId("desktop-input");
    expect(input).toHaveClass("ui-input");
    expect(input).toHaveClass("composer");
    expect(ref.current).toBe(input);
  });

  it("uses ui-input contract for select/textarea and keeps custom classes", () => {
    render(
      <>
        <Select className="picker" data-testid="desktop-select">
          <option value="one">one</option>
        </Select>
        <Textarea className="draft" data-testid="desktop-textarea" />
      </>,
    );

    const select = screen.getByTestId("desktop-select");
    const textarea = screen.getByTestId("desktop-textarea");

    expect(select.className.split("ui-input").length - 1).toBe(1);
    expect(textarea.className.split("ui-input").length - 1).toBe(1);
    expect(select).toHaveClass("picker");
    expect(textarea).toHaveClass("draft");
  });
});
