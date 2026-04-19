import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import EventTimeline from "../components/EventTimeline";

describe("EventTimeline", () => {
  it("shows empty state", () => {
    render(<EventTimeline events={[]} />);
    expect(screen.getByText("No events yet")).toBeInTheDocument();
  });

  it("filters events by input", () => {
    const events = [
      { ts: "t1", event: "RUNNER_SELECTED", context: { runner: "Codex" } },
      { ts: "t2", event: "DIFF_GATE_FAIL", context: { reason: "out_of_bounds" } },
    ];
    render(<EventTimeline events={events} />);

    const input = screen.getByPlaceholderText("Search event name or context...");
    fireEvent.change(input, { target: { value: "diff_gate" } });

    expect(screen.getByText("DIFF_GATE_FAIL")).toBeInTheDocument();
    expect(screen.queryByText("RUNNER_SELECTED")).toBeNull();
  });

  it("renders all events when filter is empty", () => {
    const events = [
      { ts: "t1", event: "RUNNER_SELECTED", context: { runner: "Codex" } },
      { ts: "t2", event: "TASK_DONE", context: { status: "ok" } },
    ];
    render(<EventTimeline events={events} />);
    expect(screen.getByText("RUNNER_SELECTED")).toBeInTheDocument();
    expect(screen.getByText("TASK_DONE")).toBeInTheDocument();
  });

  it("filters by context content", () => {
    const events = [
      { ts: "t1", event: "RUNNER_SELECTED", context: { runner: "Codex" } },
      { ts: "t2", event: "RUNNER_SELECTED", context: { runner: "Agents" } },
    ];
    render(<EventTimeline events={events} />);

    const input = screen.getByPlaceholderText("Search event name or context...");
    fireEvent.change(input, { target: { value: "agents" } });

    expect(screen.getByText("RUNNER_SELECTED")).toBeInTheDocument();
    expect(screen.getByText("Showing 1 / 2 events")).toBeInTheDocument();
    expect(screen.queryByText(/Codex/)).toBeNull();
  });

  it("handles undefined events input", () => {
    render(<EventTimeline events={undefined as any} />);
    expect(screen.getByText("No events yet")).toBeInTheDocument();
  });

  it("renders empty context fallback", () => {
    const events = [{ ts: "t1", event: "NO_CONTEXT" }];
    render(<EventTimeline events={events as any} />);

    fireEvent.click(screen.getByTestId("event-name-NO_CONTEXT"));
    expect(screen.getByText("Event drilldown")).toBeInTheDocument();
    expect(screen.getByTestId("event-drilldown-title")).toHaveTextContent("NO_CONTEXT");
    expect(screen.getByText("Key facts")).toBeInTheDocument();
  });

  it("filters when context is missing", () => {
    const events = [{ ts: "t1", event: "NO_CONTEXT" }];
    render(<EventTimeline events={events as any} />);

    const input = screen.getByPlaceholderText("Search event name or context...");
    fireEvent.change(input, { target: { value: "no_context" } });
    expect(screen.getByText("NO_CONTEXT")).toBeInTheDocument();
  });

  it("handles missing event names while filtering", () => {
    const events = [
      { ts: "t1", event: undefined, context: { mark: "fallback" } },
      { ts: "t2", event: "KNOWN_EVENT", context: { mark: "known" } },
    ];
    render(<EventTimeline events={events as any} />);

    const input = screen.getByPlaceholderText("Search event name or context...");
    fireEvent.change(input, { target: { value: "fallback" } });
    expect(screen.getByTestId("event-name-UNKNOWN")).toBeInTheDocument();
    expect(screen.queryByText("KNOWN_EVENT")).toBeNull();
  });

  it("shows empty-filter state and clears filter back to full list", () => {
    const events = [
      { ts: "t1", event: "RUNNER_SELECTED", context: { runner: "Codex" } },
      { ts: "t2", event: "DIFF_GATE_FAIL", context: { reason: "out_of_bounds" } },
    ];
    render(<EventTimeline events={events as any} />);

    fireEvent.change(screen.getByPlaceholderText("Search event name or context..."), { target: { value: "not-found" } });
    expect(screen.getByText("No events match the current filters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByText("Showing 2 / 2 events")).toBeInTheDocument();
    expect(screen.getByText("RUNNER_SELECTED")).toBeInTheDocument();
    expect(screen.getByText("DIFF_GATE_FAIL")).toBeInTheDocument();
  });

  it("covers trace_id rendering and preset buttons", () => {
    const events = [
      { ts: "t1", event: "TEST_CASE", trace_id: "trace-1", context: { stage: "test" } },
      { ts: "t2", event: "TOOL_CALL", context: { tool: "search" } },
    ];
    render(<EventTimeline events={events as any} />);

    fireEvent.click(screen.getByRole("button", { name: "Tools" }));
    expect(screen.getByText("TOOL_CALL")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tools" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("trace: trace-1")).toBeInTheDocument();
  });

  it("keeps selected event drill-down stable after filter changes", () => {
    const events = [
      { ts: "t1", event: "RUNNER_SELECTED", context: { runner: "Codex" } },
      { ts: "t2", event: "TOOL_CALL", context: { tool: "search" } },
    ];
    render(<EventTimeline events={events as any} />);

    fireEvent.click(screen.getByTestId("event-name-TOOL_CALL"));
    expect(screen.getByTestId("event-drilldown-title")).toHaveTextContent("TOOL_CALL");

    fireEvent.change(screen.getByPlaceholderText("Search event name or context..."), { target: { value: "runner" } });
    expect(screen.getByTestId("event-drilldown-title")).toHaveTextContent("TOOL_CALL");

    fireEvent.change(screen.getByPlaceholderText("Search event name or context..."), { target: { value: "" } });
    expect(screen.getByTestId("event-drilldown-title")).toHaveTextContent("TOOL_CALL");
  });

  it("exposes stable event test ids for e2e selectors", () => {
    const events = [
      { ts: "t1", event: "DIFF_GATE_FAIL", context: { reason: "out_of_bounds" } },
      { ts: "t2", event: undefined, context: { reason: "missing_event_name" } },
    ];
    render(<EventTimeline events={events as any} />);

    expect(screen.getByTestId("event-name-DIFF_GATE_FAIL")).toBeInTheDocument();
    expect(screen.getByTestId("event-name-UNKNOWN")).toBeInTheDocument();
  });

  it("shows semantic drill-down for runner/worktree/mcp events", () => {
    const events = [
      { ts: "t1", event: "RUNNER_SELECTED", context: { runner: "codex", provider: "openai", model: "gpt-5" } },
      { ts: "t2", event: "WORKTREE_CREATED", context: { worktree: "/tmp/w1", branch: "feat/a", base: "main" } },
      { ts: "t3", event: "MCP_CONCURRENCY_CHECK", context: { concurrency: 4, mode: "strict", scope: "default" } },
    ];
    render(<EventTimeline events={events as any} />);

    fireEvent.click(screen.getByTestId("event-name-RUNNER_SELECTED"));
    expect(screen.getByTestId("event-selection-status")).toHaveTextContent("RUNNER_SELECTED");
    expect(screen.getByText("Runner: codex")).toBeInTheDocument();
    expect(screen.getByText("Provider: openai")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("event-name-WORKTREE_CREATED"));
    expect(screen.getByTestId("event-selection-status")).toHaveTextContent("WORKTREE_CREATED");
    expect(screen.getByText("Worktree: /tmp/w1")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("event-name-MCP_CONCURRENCY_CHECK"));
    expect(screen.getByTestId("event-selection-status")).toHaveTextContent("MCP_CONCURRENCY_CHECK");
    expect(screen.getByText("Concurrency limit: 4")).toBeInTheDocument();
  });

  it("shows in-row selected marker after click", () => {
    const events = [
      { ts: "t1", event: "WORKTREE_CREATED", context: { worktree: "/tmp/w1" } },
      { ts: "t2", event: "RUNNER_SELECTED", context: { runner: "codex" } },
    ];
    render(<EventTimeline events={events as any} />);

    fireEvent.click(screen.getByTestId("event-name-WORKTREE_CREATED"));
    expect(screen.getByText(/Worktree change · selected/)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("event-name-RUNNER_SELECTED"));
    expect(screen.getByText(/Runner decision · selected/)).toBeInTheDocument();
  });

  it("calls onEventInspect and surfaces refresh notice", () => {
    const onEventInspect = vi.fn();
    const events = [{ ts: "t1", event: "WORKTREE_CREATED", context: { worktree: "/tmp/w1" } }];
    render(<EventTimeline events={events as any} onEventInspect={onEventInspect} />);

    fireEvent.click(screen.getByTestId("event-name-WORKTREE_CREATED"));
    expect(onEventInspect).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("event-inspect-notice")).toHaveTextContent("Refreshed the linked execution logs for WORKTREE_CREATED");

    fireEvent.click(screen.getByTestId("event-drilldown-refresh"));
    expect(onEventInspect).toHaveBeenCalledTimes(2);
  });

  it("covers status classes for failed, success, warning, and running events", () => {
    const events = [
      { ts: "t1", event: "DIFF_GATE_FAIL", context: {} },
      { ts: "t2", event: "TASK_DONE", context: {} },
      { ts: "t3", event: "HUMAN_APPROVAL_REQUIRED", context: {} },
      { ts: "t4", event: "RUNNER_ACTIVE", context: {} },
    ];
    const { container } = render(<EventTimeline events={events as any} />);

    const cards = Array.from(container.querySelectorAll(".event-item"));
    expect(cards[0]).toHaveClass("event-card--failed");
    expect(cards[1]).toHaveClass("event-card--success");
    expect(cards[2]).toHaveClass("event-card--warning");
    expect(cards[3]).toHaveClass("event-card--running");
  });

  it("renders zh-CN preset, filter, and clear copy", () => {
    const events = [{ ts: "t1", event: "RUNNER_SELECTED", context: { runner: "Codex" } }];
    render(<EventTimeline events={events as any} locale="zh-CN" />);

    expect(screen.getByRole("button", { name: "全部" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "工具" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "差异" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "审批" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "测试" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "门禁" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("搜索事件名称或上下文...")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("搜索事件名称或上下文..."), { target: { value: "missing" } });
    expect(screen.getByText("当前筛选下没有匹配事件")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "清空筛选" }));
    expect(screen.getByText("显示 1 / 1 条事件")).toBeInTheDocument();
  });

  it("shows zh-CN action meanings and localized key facts for common event families", () => {
    const events = [
      { ts: "t1", event: "RUNNER_SELECTED", context: { runner: "codex", provider: "openai", model: "gpt-5" } },
      { ts: "t2", event: "WORKTREE_CREATED", context: { worktree: "/tmp/w1", branch: "feat/a", base: "main" } },
      { ts: "t3", event: "MCP_CONCURRENCY_CHECK", context: { concurrency: 4, mode: "strict", scope: "default" } },
      { ts: "t4", event: "DIFF_PATCH_APPLIED", context: { patch: "ok" } },
      { ts: "t5", event: "HUMAN_APPROVAL_PENDING", context: { approver: "pm" } },
      { ts: "t6", event: "TEST_SUITE_FINISHED", context: { suite: "ui" } },
      { ts: "t7", event: "POLICY_REVIEW", context: { state: "warn" } },
      { ts: "t8", event: "CUSTOM_EVENT", context: { custom: "value" } },
    ];
    render(<EventTimeline events={events as any} locale="zh-CN" />);

    fireEvent.click(screen.getByTestId("event-name-RUNNER_SELECTED"));
    expect(screen.getByTestId("event-selection-status")).toHaveTextContent("已选：RUNNER_SELECTED · 执行器决策");
    expect(screen.getByText("执行器: codex")).toBeInTheDocument();
    expect(screen.getByText("提供方: openai")).toBeInTheDocument();
    expect(screen.getByText("模型: gpt-5")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("event-name-WORKTREE_CREATED"));
    expect(screen.getByTestId("event-selection-status")).toHaveTextContent("工作树变更");
    expect(screen.getByText("工作树: /tmp/w1")).toBeInTheDocument();
    expect(screen.getByText("分支: feat/a")).toBeInTheDocument();
    expect(screen.getByText("基线: main")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("event-name-MCP_CONCURRENCY_CHECK"));
    expect(screen.getByTestId("event-selection-status")).toHaveTextContent("工具并发检查");
    expect(screen.getByText("并发上限: 4")).toBeInTheDocument();
    expect(screen.getByText("策略模式: strict")).toBeInTheDocument();
    expect(screen.getByText("范围: default")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("event-name-DIFF_PATCH_APPLIED"));
    expect(screen.getByTestId("event-selection-status")).toHaveTextContent("补丁与差异");

    fireEvent.click(screen.getByTestId("event-name-HUMAN_APPROVAL_PENDING"));
    expect(screen.getByTestId("event-selection-status")).toHaveTextContent("人工审批");

    fireEvent.click(screen.getByTestId("event-name-TEST_SUITE_FINISHED"));
    expect(screen.getByTestId("event-selection-status")).toHaveTextContent("测试执行");

    fireEvent.click(screen.getByTestId("event-name-POLICY_REVIEW"));
    expect(screen.getByTestId("event-selection-status")).toHaveTextContent("策略检查");

    fireEvent.click(screen.getByTestId("event-name-CUSTOM_EVENT"));
    expect(screen.getByTestId("event-selection-status")).toHaveTextContent("系统事件");
    expect(screen.getByText("custom: value")).toBeInTheDocument();
  });
});
