import { describe, expect, it } from "vitest";
import {
  formatDashboardDateTime,
  badgeClass,
  statusLabel,
  statusLabelDefault,
  knownOutcomeTypeLabelZh,
  outcomeTypeLabelZh,
  stageCtaZh,
  stageLabelZh,
  stageVariant,
  statusCtaZh,
  statusDotClass,
  statusVariant,
  statusLabelZh,
} from "../lib/statusPresentation";

describe("statusLabelDefault", () => {
  it("maps common states to canonical default-locale labels", () => {
    expect(statusLabelDefault("success")).toBe("Completed");
    expect(statusLabelDefault("running")).toBe("Running");
    expect(statusLabelDefault("blocked")).toBe("Blocked");
    expect(statusLabelDefault("failed")).toBe("Failed");
    expect(statusLabelDefault("paused")).toBe("Paused");
    expect(statusLabelDefault("archived")).toBe("Archived");
  });

  it("returns fallback for unknown values", () => {
    expect(statusLabelDefault("")).toBe("Unknown");
    expect(statusLabelDefault("new_state")).toBe("Unknown");
  });
});

describe("locale-aware presentation foundation", () => {
  it("supports explicit locale labels without changing English-first defaults", () => {
    expect(statusLabel("success")).toBe("Completed");
    expect(statusLabelZh("success")).toBe("已完成");
    expect(statusLabel("success", "zh-CN")).toBe("已完成");
    expect(statusLabel("running", "zh-CN")).toBe("运行中");
  });

  it("formats dashboard timestamps with locale-aware defaults", () => {
    const timestamp = "2026-02-02T00:00:00Z";
    expect(formatDashboardDateTime(timestamp, "en", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })).toBe(new Date(timestamp).toLocaleString("en", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }));
    expect(formatDashboardDateTime(timestamp, "zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })).toBe(new Date(timestamp).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }));
  });
});

describe("status presentation helpers", () => {
  it("maps status variant classes and cta consistently", () => {
    expect(statusVariant("approved")).toBe("success");
    expect(statusVariant("timeout")).toBe("failed");
    expect(statusVariant("working")).toBe("running");
    expect(statusVariant("pending")).toBe("warning");
    expect(statusVariant("unmapped")).toBe("default");

    expect(statusDotClass("approved")).toBe("status-dot status-dot--success");
    expect(statusDotClass("timeout")).toBe("status-dot status-dot--danger");
    expect(statusDotClass("working")).toBe("status-dot status-dot--primary");
    expect(statusDotClass("pending")).toBe("status-dot status-dot--warning");
    expect(statusDotClass("unmapped")).toBe("status-dot");

    expect(badgeClass("approved")).toBe("badge badge--success");
    expect(badgeClass("timeout")).toBe("badge badge--failed");
    expect(badgeClass("working")).toBe("badge badge--running");
    expect(badgeClass("pending")).toBe("badge badge--warning");
    expect(badgeClass("unmapped")).toBe("badge");

    expect(statusCtaZh("running")).toBe("查看进度");
    expect(statusCtaZh("paused")).toBe("恢复运行");
    expect(statusCtaZh("unknown")).toBe("查看详情");
    expect(statusCtaZh("")).toBe("查看详情");
  });

  it("maps stage label variant and cta consistently", () => {
    expect(stageLabelZh("planning")).toBe("规划");
    expect(stageLabelZh("analysis")).toBe("发现");
    expect(stageLabelZh("execution")).toBe("执行");
    expect(stageLabelZh("qa")).toBe("验证");
    expect(stageLabelZh("release")).toBe("发布");
    expect(stageLabelZh("done")).toBe("完成");
    expect(stageLabelZh("unknown")).toBe("未知阶段");

    expect(stageVariant("planning")).toBe("todo");
    expect(stageVariant("analysis")).toBe("active");
    expect(stageVariant("execution")).toBe("active");
    expect(stageVariant("qa")).toBe("verify");
    expect(stageVariant("release")).toBe("verify");
    expect(stageVariant("done")).toBe("done");
    expect(stageVariant("unknown")).toBe("default");

    expect(stageCtaZh("todo")).toBe("开始接单");
    expect(stageCtaZh("plan")).toBe("确认方案");
    expect(stageCtaZh("verify")).toBe("处理审查");
    expect(stageCtaZh("release")).toBe("开始发布");
    expect(stageCtaZh("done")).toBe("查看结果");
    expect(stageCtaZh("unknown")).toBe("查看详情");
    expect(stageCtaZh("")).toBe("查看详情");
  });
});

describe("outcome type presentation helpers", () => {
  it("maps unified outcome labels without legacy wording", () => {
    expect(knownOutcomeTypeLabelZh("gate")).toBe("Gate 被阻塞");
    expect(knownOutcomeTypeLabelZh("manual")).toBe("需要人工确认");
    expect(knownOutcomeTypeLabelZh("env")).toBe("环境异常");
    expect(knownOutcomeTypeLabelZh("product")).toBe("功能失败");
    expect(knownOutcomeTypeLabelZh("functional_failure")).toBe("功能失败");
    expect(knownOutcomeTypeLabelZh("unknown")).toBe("失败原因待确认");
    expect(knownOutcomeTypeLabelZh("not_exists")).toBeUndefined();

    expect(outcomeTypeLabelZh("gate_blocked")).toBe("Gate 被阻塞");
    expect(outcomeTypeLabelZh("manual_pending")).toBe("需要人工确认");
    expect(outcomeTypeLabelZh("environment_error")).toBe("环境异常");
    expect(outcomeTypeLabelZh("functional_failure")).toBe("功能失败");
    expect(outcomeTypeLabelZh("not_exists")).toBe("未分类");
  });
});
