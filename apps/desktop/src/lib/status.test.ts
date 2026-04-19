import { describe, expect, it } from "vitest";
import { alertSeverityToBadge, sessionStatusToBadge } from "./status";
import {
  outcomeActionHintZh,
  outcomeSemantic,
  outcomeSemanticBadgeClass,
  outcomeSemanticLabelZh,
  stageCtaZh,
  stageLabelZh,
  stageVariant,
  statusCtaZh,
  statusDotClass,
  statusLabelZh,
  statusVariant,
} from "./statusPresentation";

describe("status mapping", () => {
  it("maps session statuses to localized labels", () => {
    expect(sessionStatusToBadge("running")).toEqual({ tone: "running", label: "Running" });
    expect(sessionStatusToBadge("active")).toEqual({ tone: "running", label: "Running" });
    expect(sessionStatusToBadge("blocked")).toEqual({ tone: "warning", label: "Blocked" });
    expect(sessionStatusToBadge("completed")).toEqual({ tone: "completed", label: "Completed" });
    expect(sessionStatusToBadge("failed")).toEqual({ tone: "critical", label: "Critical" });
    expect(sessionStatusToBadge("unknown-state")).toEqual({ tone: "warning", label: "Needs review" });
  });

  it("maps alert severities to localized labels", () => {
    expect(alertSeverityToBadge("critical")).toEqual({ tone: "critical", label: "Critical" });
    expect(alertSeverityToBadge("warning")).toEqual({ tone: "warning", label: "Warning" });
    expect(alertSeverityToBadge("info")).toEqual({ tone: "running", label: "Info" });
    expect(alertSeverityToBadge("unknown")).toEqual({ tone: "warning", label: "Needs review" });
  });
});

describe("statusPresentation outcome semantics", () => {
  it("prioritizes explicit failureClass mapping", () => {
    expect(outcomeSemantic(undefined, "running", "gate", undefined)).toBe("gate_blocked");
    expect(outcomeSemantic(undefined, "running", "manual", undefined)).toBe("manual_pending");
    expect(outcomeSemantic(undefined, "running", "env", undefined)).toBe("environment_error");
    expect(outcomeSemantic(undefined, "running", "product", undefined)).toBe("functional_failure");
  });

  it("derives semantic from outcome type tokens", () => {
    expect(outcomeSemantic("policy_gate_blocked", "running", undefined, undefined)).toBe("gate_blocked");
    expect(outcomeSemantic("needs_human_approval", "running", undefined, undefined)).toBe("manual_pending");
    expect(outcomeSemantic("runtime_infra_failure", "running", undefined, undefined)).toBe("environment_error");
    expect(outcomeSemantic("biz_logic_mismatch", "running", undefined, undefined)).toBe("functional_failure");
  });

  it("derives semantic from normalized failure code tokens", () => {
    expect(outcomeSemantic(undefined, "running", undefined, "gate_policy_denied")).toBe("gate_blocked");
    expect(outcomeSemantic(undefined, "running", undefined, "approval_required")).toBe("manual_pending");
    expect(outcomeSemantic(undefined, "running", undefined, "runtime_worker_crash")).toBe("environment_error");
    expect(outcomeSemantic(undefined, "running", undefined, "logic_assertion_error")).toBe("functional_failure");
    expect(outcomeSemantic(undefined, "running", undefined, "diff_gate_mismatch")).toBe("gate_blocked");
    expect(outcomeSemantic(undefined, "running", undefined, "ROLLBACK_FAILURE")).toBe("environment_error");
  });

  it("falls back to status token and unknown when no signal provided", () => {
    expect(outcomeSemantic(undefined, "blocked", undefined, undefined)).toBe("manual_pending");
    expect(outcomeSemantic(undefined, "failed", undefined, undefined)).toBe("functional_failure");
    expect(outcomeSemantic(undefined, "running", undefined, undefined)).toBe("unknown");
    expect(outcomeSemantic(undefined, undefined, undefined, null)).toBe("unknown");
  });

  it("resolves semantic labels and action hints with explicit override", () => {
    expect(outcomeSemanticLabelZh(undefined, "  Human review  ", "failed")).toBe("Human review");
    expect(outcomeSemanticLabelZh(undefined, "  人工判定  ", "failed")).toBe("Functional failure");
    expect(outcomeSemanticLabelZh("policy_gate", "", "running")).toBe("Gate blocked");
    expect(outcomeSemanticLabelZh("runtime_error", undefined, "running")).toBe("Environment issue");
    expect(outcomeSemanticLabelZh("needs_approval", undefined, "running")).toBe("Manual confirmation required");
    expect(outcomeSemanticLabelZh("biz_failure", undefined, "running")).toBe("Functional failure");
    expect(outcomeSemanticLabelZh(undefined, undefined, "running")).toBe("Status pending confirmation");

    expect(outcomeActionHintZh("  Handle directly  ", undefined, "running")).toBe("Handle directly");
    expect(outcomeActionHintZh(undefined, "policy_gate", "running")).toBe("Adjust the gate and retry");
    expect(outcomeActionHintZh(undefined, "runtime_error", "running")).toBe("Check the environment and dependencies, then retry");
    expect(outcomeActionHintZh(undefined, "needs_approval", "running")).toBe("Complete manual confirmation before continuing");
    expect(outcomeActionHintZh(undefined, "biz_failure", "running")).toBe("Fix the functional issue and retry");
    expect(outcomeActionHintZh(undefined, undefined, "running")).toBe("View details and continue investigating");
  });

  it("maps badge class from semantic fallback rules", () => {
    expect(outcomeSemanticBadgeClass("policy_gate", "running")).toBe("ui-badge ui-badge--warning");
    expect(outcomeSemanticBadgeClass("needs_approval", "running")).toBe("ui-badge ui-badge--warning");
    expect(outcomeSemanticBadgeClass("runtime_error", "running")).toBe("ui-badge ui-badge--failed");
    expect(outcomeSemanticBadgeClass("biz_failure", "running")).toBe("ui-badge ui-badge--failed");
    expect(outcomeSemanticBadgeClass(undefined, "running")).toBe("ui-badge ui-badge--running");
  });
});

describe("statusPresentation canonical wrappers", () => {
  it("returns localized status and stage metadata", () => {
    expect(statusLabelZh("completed")).toBe("已完成");
    expect(statusCtaZh("failed")).toBe("复盘失败并重试");
    expect(statusVariant("running")).toBe("running");
    expect(statusDotClass("paused")).toContain("dot");

    expect(stageLabelZh("execution")).toBe("执行");
    expect(stageCtaZh("verify")).toBe("处理审查");
    expect(stageVariant("unknown-stage")).toBe("default");
  });
});
