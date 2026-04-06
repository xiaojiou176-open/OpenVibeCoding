import { createElement, isValidElement } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  buildNodeStyle,
  createSeedTimeline,
  nextLayoutMode,
  nodeIcon,
  renderChatEmbed
} from "./desktopUi";

describe("desktopUi seed timeline", () => {
  it("preselects bootstrap decision to avoid first-entry false blocking", () => {
    const timeline = createSeedTimeline("pm-seed");
    const decision = timeline[0]?.embeds?.find((embed) => embed.kind === "decision");
    expect(decision).toMatchObject({ kind: "decision", selected: "strict" });
    if (!decision || decision.kind !== "decision") {
      throw new Error("bootstrap decision missing");
    }
    expect(decision.selected).toBe("strict");
  });

  it("renders report embed action and triggers view-diff callback", () => {
    const onViewDiff = vi.fn();
    const message = {
      id: "msg-1",
      role: "pm",
      content: "report",
      embeds: [],
    } as const;

    const embed = {
      id: "report-1",
      kind: "report",
      linkedNodeId: "rv",
      title: "执行结果",
      summary: "summary",
      files: ["apps/desktop/src/App.tsx"],
      tests: "npm run desktop:test",
    } as const;

    render(
      createElement(
        "div",
        null,
        renderChatEmbed(message as any, embed as any, vi.fn(), {
          onViewDiff,
        }),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "查看完整 Diff" }));
    expect(onViewDiff).toHaveBeenCalledWith("report-1");
  });

  it("cycles layout mode with explicit fallback", () => {
    expect(nextLayoutMode("dialog")).toBe("split");
    expect(nextLayoutMode("split")).toBe("dialog");
    expect(nextLayoutMode("chain")).toBe("dialog");
    expect(nextLayoutMode("focus")).toBe("dialog");
  });

  it("builds node style for each status branch", () => {
    expect(buildNodeStyle("working", true)).toMatchObject({
      border: "2px solid var(--chain-node-working-border)",
      boxShadow: "0 0 0 3px var(--chain-node-working-shadow)"
    });
    expect(buildNodeStyle("done", false)).toMatchObject({
      border: "1.5px solid var(--chain-node-done-border)",
      boxShadow: "none"
    });
    expect(buildNodeStyle("failed", true)).toMatchObject({
      border: "2px solid var(--chain-node-failed-border)"
    });
    expect(buildNodeStyle("waiting", false)).toMatchObject({
      border: "1.5px dashed var(--chain-node-waiting-border)"
    });
    expect(buildNodeStyle("idle", true)).toMatchObject({
      border: "1.5px solid var(--chain-node-idle-border)"
    });
  });

  it("returns role icon element for known and unknown roles", () => {
    const known = nodeIcon("PM");
    const unknown = nodeIcon("Unknown");
    expect(isValidElement(known)).toBe(true);
    expect(isValidElement(unknown)).toBe(true);
    expect((known as { props?: { size?: number } }).props?.size).toBe(16);
    expect((unknown as { props?: { size?: number } }).props?.size).toBe(16);
    expect((known as { type?: unknown }).type).not.toBe((unknown as { type?: unknown }).type);
  });

  it("renders decision embed and dispatches chooseDecision with factual ids", () => {
    const chooseDecision = vi.fn();
    const message = { id: "msg-decision", role: "pm", content: "decision", embeds: [] } as const;
    const embed = {
      id: "decision-1",
      kind: "decision",
      linkedNodeId: "pm",
      title: "决策",
      description: "desc",
      selected: "strict",
      options: [
        { id: "strict", title: "严格验收", summary: "s1", risk: "r1", recommended: true },
        { id: "fast", title: "快速探索", summary: "s2", risk: "r2" }
      ]
    } as const;

    render(createElement("div", null, renderChatEmbed(message as any, embed as any, chooseDecision)));

    expect(screen.getByText("推荐")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "选择" }));
    expect(chooseDecision).toHaveBeenCalledWith("msg-decision", "decision-1", "fast");
  });

  it("renders delegation/progress/alert embeds with expected status signals", () => {
    const message = { id: "msg-embed", role: "pm", content: "embeds", embeds: [] } as const;
    const chooseDecision = vi.fn();

    const delegation = {
      id: "delegation-1",
      kind: "delegation",
      linkedNodeId: "tl",
      title: "TL 委派",
      task: "拆分任务",
      plan: "并发执行",
      status: "进行中"
    } as const;
    const progress = {
      id: "progress-1",
      kind: "progress",
      linkedNodeId: "w1",
      title: "执行进度",
      updates: [
        { actor: "W1", detail: "编码", state: "working" },
        { actor: "W2", detail: "测试", state: "pending" },
        { actor: "RV", detail: "验收", state: "done" }
      ]
    } as const;
    const alert = {
      id: "alert-1",
      kind: "alert",
      linkedNodeId: "gate",
      title: "门禁告警",
      level: "critical",
      description: "覆盖率不足",
      action: "补齐测试"
    } as const;

    render(
      createElement(
        "div",
        null,
        renderChatEmbed(message as any, delegation as any, chooseDecision),
        renderChatEmbed(message as any, progress as any, chooseDecision),
        renderChatEmbed(message as any, alert as any, chooseDecision)
      )
    );

    expect(screen.getByText("任务：")).toBeInTheDocument();
    expect(screen.getAllByText("进行中")).toHaveLength(2);
    expect(screen.getByText("等待")).toBeInTheDocument();
    expect(screen.getByText("完成")).toBeInTheDocument();
    expect(screen.getByLabelText("警报卡片")).toHaveClass("is-critical");
  });
});
