import { fireEvent, render, screen } from "@testing-library/react";
import * as Diff2Html from "diff2html";
import { vi } from "vitest";
import DiffViewer, { sanitizeHtml } from "../components/DiffViewer";

test("renders diff2html output", () => {
  const diff = [
    "diff --git a/file.txt b/file.txt",
    "index 0000000..1111111 100644",
    "--- a/file.txt",
    "+++ b/file.txt",
    "@@ -0,0 +1 @@",
    "+hello",
  ].join("\n");

  const { container } = render(<DiffViewer diff={diff} allowedPaths={["file.txt"]} />);
  const wrapper = container.querySelector(".d2h-file-wrapper");
  expect(wrapper).not.toBeNull();
});

test("shows empty state when diff missing", () => {
  const { container } = render(<DiffViewer diff="" allowedPaths={[]} />);
  expect(container.textContent).toContain("No code changes are available yet.");
});

test("marks out-of-bounds files and keeps rendering when parser or renderer fails", () => {
  const diff = [
    "diff --git a/apps/a.ts b/apps/a.ts",
    "index 0000000..1111111 100644",
    "--- a/apps/a.ts",
    "+++ b/apps/a.ts",
    "@@ -0,0 +1 @@",
    "+console.log('a')",
  ].join("\n");

  const { container, rerender } = render(<DiffViewer diff={diff} allowedPaths={["docs"]} />);
  expect(container.textContent).toContain("Files outside the assigned scope were detected.");
  expect(container.textContent).toContain("apps/a.ts");

  const htmlSpy = vi.spyOn(Diff2Html, "html").mockImplementationOnce(() => {
    throw new Error("render failed");
  });
  rerender(<DiffViewer diff={diff} allowedPaths={[]} />);
  expect(container.querySelector(".diff-viewer")).not.toBeNull();
  expect(container.textContent).toContain("render failed");
  expect(container.textContent).toContain("diff --git a/apps/a.ts b/apps/a.ts");
  htmlSpy.mockRestore();

  const parseSpy = vi.spyOn(Diff2Html, "parse").mockImplementationOnce(() => {
    throw new Error("parse failed");
  });
  rerender(<DiffViewer diff={"diff --git malformed"} allowedPaths={[]} />);
  expect(container.querySelector(".diff-viewer")).not.toBeNull();
  expect(container.textContent).toContain("parse failed");
  parseSpy.mockRestore();
});

test("uses onRetry callback when retry actions are clicked", () => {
  const onRetry = vi.fn();
  render(<DiffViewer diff="" allowedPaths={[]} onRetry={onRetry} />);

  fireEvent.click(screen.getByRole("button", { name: "Refresh this page" }));
  expect(onRetry).toHaveBeenCalledTimes(1);
});

test("sanitizes dangerous protocol and inline event attributes", () => {
  const dirty = [
    "<script>alert(1)</script>",
    '<a href="javascript:alert(1)" onclick="alert(1)">unsafe</a>',
    "<div>safe</div>",
  ].join("");
  const clean = sanitizeHtml(dirty);

  expect(clean).not.toContain("<script");
  expect(clean).not.toContain("javascript:");
  expect(clean).not.toContain("onclick=");
  expect(clean).toContain("safe");
});
