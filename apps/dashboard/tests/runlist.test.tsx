import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { render, screen, within } from "@testing-library/react";

import RunList from "../components/RunList";
import { sanitizeHtml } from "../components/DiffViewer";

function readCssBundle(entryPath: string, visited: Set<string> = new Set()): string {
  if (!existsSync(entryPath) || visited.has(entryPath)) {
    return "";
  }
  visited.add(entryPath);
  const css = readFileSync(entryPath, "utf8");
  const imports = [...css.matchAll(/@import\s+["'](.+?)["'];/g)];
  let bundledCss = css;
  for (const match of imports) {
    const importTarget = match[1];
    if (!importTarget.endsWith(".css")) {
      continue;
    }
    bundledCss += `\n${readCssBundle(resolve(dirname(entryPath), importTarget), visited)}`;
  }
  return bundledCss;
}

test("renders run list items", () => {
  const expectedTime = new Date("2026-02-02T00:00:00Z").toLocaleString("en", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  render(
    <RunList
      runs={[
        { run_id: "run-001", task_id: "task-001", status: "done", created_at: "2026-02-02T00:00:00Z" },
      ]}
    />
  );

  const row = screen.getByRole("row", { name: /run-001/i });
  expect(within(row).getByRole("link", { name: "run-001" })).toHaveAttribute("href", "/runs/run-001");
  expect(within(row).getByText("Task: task-001")).toBeInTheDocument();
  expect(within(row).getByText("Completed")).toBeInTheDocument();
  expect(within(row).getAllByText("The outcome is ready for proof review.").length).toBeGreaterThan(0);
  expect(within(row).getByRole("link", { name: "Open run detail" })).toHaveAttribute("href", "/runs/run-001");
  expect(within(row).getByText(expectedTime)).toBeInTheDocument();
});

test("supports explicit zh-CN rendering through locale-aware props", () => {
  const expectedTime = new Date("2026-02-02T00:00:00Z").toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  render(
    <RunList
      locale="zh-CN"
      runs={[
        { run_id: "run-zh", task_id: "task-zh", status: "done", created_at: "2026-02-02T00:00:00Z" },
      ]}
    />
  );

  const row = screen.getByRole("row", { name: /run-zh/i });
  expect(within(row).getByText("已完成")).toBeInTheDocument();
  expect(within(row).getByText(expectedTime)).toBeInTheDocument();
});

test("shows empty state when no runs", () => {
  render(<RunList runs={[]} />);
  expect(screen.getByText("No runs yet.")).toBeInTheDocument();
  const cta = screen.getByRole("link", { name: "Create your first task in PM" });
  expect(cta).toHaveAccessibleName("Create your first task in PM");
  expect(cta).toHaveAttribute("href", "/pm");
  expect(cta).toBeVisible();
});

test("renders placeholder when created_at missing", () => {
  render(<RunList runs={[{ run_id: "run-002", task_id: "task-002", status: "queued" }]} />);
  const row = screen.getByRole("row", { name: /run-002/i });
  expect(within(row).getByRole("link", { name: "run-002" })).toBeInTheDocument();
  expect(within(row).getByText("Unknown")).toBeInTheDocument();
  expect(within(row).getAllByText("This run has not reported a clear proof posture yet.").length).toBeGreaterThan(0);
});

test("handles null status without crashing", () => {
  render(
    <RunList
      runs={[
        {
          run_id: "run-003",
          task_id: "task-003",
          status: null as unknown as string,
        },
      ]}
    />
  );

  const row = screen.getByRole("row", { name: /run-003/i });
  expect(within(row).getByRole("link", { name: "run-003" })).toBeInTheDocument();
  expect(within(row).getByText("Unknown")).toBeInTheDocument();
});

test("covers fallback fields and badge classes", () => {
  render(
    <RunList
      runs={[
        {
          run_id: "   ",
          task_id: "",
          status: "FAILURE",
          workflow_status: "WF_RUNNING",
          start_ts: "2026-02-10T00:00:00Z",
          owner_role: "PM",
          owner_agent_id: "agent-1",
          assigned_role: "Worker",
          assigned_agent_id: "agent-2",
          last_event_ts: "2026-02-10T00:00:01Z",
          failure_reason: "diff gate",
        },
      ]}
    />
  );

  const row = screen.getByRole("row", { name: /unknown-run/i });
  expect(within(row).queryByRole("link", { name: "unknown-run" })).toBeNull();
  expect(within(row).getByText("unknown-run")).toHaveAttribute("aria-disabled", "true");
  expect(within(row).getByText(/\(agent-1\)/)).toBeInTheDocument();
  expect(within(row).getByText(/\(agent-2\)/)).toBeInTheDocument();
  expect(within(row).getByText("Failed")).toHaveClass("badge--failed");
  expect(row).toHaveClass("session-row--failed");
  expect(within(row).getByText("Workflow: WF_RUNNING")).toBeInTheDocument();
  expect(within(row).getByText("diff gate")).toBeInTheDocument();
});

test("treats statuses containing FAILURE as failed style", () => {
  render(
    <RunList
      runs={[
        {
          run_id: "run-failure-token",
          task_id: "task-failure-token",
          status: "WORKER_FAILURE_TIMEOUT",
        },
      ]}
    />,
  );
  const row = screen.getByRole("link", { name: /run-failure-/i }).closest("tr") as HTMLElement;
  expect(within(row).getByText("Failed")).toHaveClass("badge--failed");
  expect(row).toHaveClass("session-row--failed");
});

test("uses unified status mapping for labels and classes", () => {
  render(
    <RunList
      runs={[
        { run_id: "run-approved", task_id: "task-approved", status: "approved" },
        { run_id: "run-running", task_id: "task-running", status: "running" },
      ]}
    />
  );

  const successRow = screen.getByRole("row", { name: /run-approved/i });
  expect(within(successRow).getByText("Completed")).toHaveClass("badge--success");

  const runningRow = screen.getByRole("row", { name: /run-running/i });
  expect(within(runningRow).getByText("Running")).toHaveClass("badge--running");
  expect(runningRow).toHaveClass("session-row--running");
});

test("renders concise failure summary with single-run actions only", () => {
  render(
    <RunList
      runs={[
        {
          run_id: "run-gate",
          task_id: "task-gate",
          status: "FAILED",
          failure_reason: "policy rejected",
          failure_class: "gate",
        },
        {
          run_id: "run-manual",
          task_id: "task-manual",
          status: "FAILED",
          failure_reason: "needs approval",
          failure_class: "manual",
        },
        {
          run_id: "run-product",
          task_id: "task-product",
          status: "FAILED",
          failure_reason: "assertion mismatch",
          failure_class: "product",
        },
      ]}
    />
  );

  expect(screen.getByText("policy rejected")).toBeInTheDocument();
  expect(screen.getByText("needs approval")).toBeInTheDocument();
  expect(screen.getByText("assertion mismatch")).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: "Open Proof & Replay" })).toHaveLength(3);
  const timelineLinks = screen.getAllByRole("link", { name: "Open event timeline" });
  expect(timelineLinks).toHaveLength(3);
  expect(timelineLinks[0]).toHaveAttribute("href", "/events?run_id=run-gate");
  expect(timelineLinks[1]).toHaveAttribute("href", "/events?run_id=run-manual");
  expect(timelineLinks[2]).toHaveAttribute("href", "/events?run_id=run-product");
});

test("keeps failure summary as the primary text and removes duplicate hint noise", () => {
  render(
    <RunList
      runs={[
        {
          run_id: "run-dup-hint",
          task_id: "task-dup-hint",
          status: "FAILED",
          failure_reason: "worker timeout",
          action_hint_zh: "worker timeout",
          failure_class: "runtime",
        },
      ]}
    />
  );

  const row = screen.getByRole("row", { name: /run-dup-hint/i });
  expect(within(row).getAllByText("worker timeout").length).toBeGreaterThan(0);
  expect(within(row).getByRole("link", { name: "Open Proof & Replay" })).toHaveAttribute("href", "/runs/run-dup-hint");
});

test("sanitizes dangerous diff html payloads", () => {
  const sanitized = sanitizeHtml(`
    <div onclick="alert('xss')">safe</div>
    <a href="javascript:alert('xss')">link</a>
    <iframe srcdoc="<script>alert('xss')</script>"></iframe>
  `);
  expect(sanitized).toContain("<div>safe</div>");
  expect(sanitized).toContain("<a>link</a>");
  expect(sanitized).not.toContain("onclick=");
  expect(sanitized).not.toContain("javascript:");
  expect(sanitized).not.toContain("<iframe");
  expect(sanitized).not.toContain("srcdoc=");
});

test("keeps contrast-safe muted and badge text tokens in dashboard globals", () => {
  const cssPath = (() => {
    try {
      return fileURLToPath(new URL("../app/globals.css", import.meta.url));
    } catch {
      return resolve(process.cwd(), "app/globals.css");
    }
  })();
  const css = readCssBundle(cssPath);

  expect(css).toContain("--color-text-muted: #4b5563;");
  expect(css).toContain("--color-success-ink: #065f46;");
  expect(css).toContain("--color-warning-ink: #92400e;");
  expect(css).toContain("--color-danger-ink: #b91c1c;");
  expect(css).toContain(".quick-card-desc");
  expect(css).toContain(".ct-home-filter-desc");
  expect(css).toContain(".sidebar-link");
});
