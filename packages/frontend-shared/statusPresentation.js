const STATUS_ALIASES = {
    active: "running",
    approve: "completed",
    approved: "completed",
    archived: "archived",
    blocked: "blocked",
    canceled: "cancelled",
    cancelled: "cancelled",
    closed: "archived",
    completed: "completed",
    critical: "failed",
    degraded: "blocked",
    denied: "failed",
    done: "completed",
    error: "failed",
    executing: "running",
    fail: "failed",
    failed: "failed",
    failure: "failed",
    healthy: "healthy",
    idle: "idle",
    in_progress: "running",
    info: "info",
    ok: "completed",
    on_hold: "blocked",
    pass: "completed",
    passed: "completed",
    paused: "paused",
    pending: "pending",
    progress: "running",
    reject: "failed",
    rejected: "failed",
    running: "running",
    success: "completed",
    timeout: "failed",
    waiting: "pending",
    warning: "blocked",
    working: "running",
};
const STATUS_LABELS_BY_LOCALE = {
    en: {
        archived: "Archived",
        blocked: "Blocked",
        cancelled: "Cancelled",
        completed: "Completed",
        failed: "Failed",
        healthy: "Healthy",
        idle: "Idle",
        info: "Info",
        paused: "Paused",
        pending: "Pending",
        running: "Running",
    },
    "zh-CN": {
        archived: "已归档",
        blocked: "已阻塞",
        cancelled: "已取消",
        completed: "已完成",
        failed: "失败",
        healthy: "健康",
        idle: "空闲",
        info: "信息",
        paused: "已暂停",
        pending: "待处理",
        running: "运行中",
    },
};
const OUTCOME_TYPE_LABELS_BY_LOCALE = {
    en: {
        blocked: "Blocked",
        env: "Environment issue",
        environment_error: "Environment issue",
        gate: "Gate blocked",
        gate_blocked: "Gate blocked",
        manual: "Manual confirmation required",
        manual_pending: "Manual confirmation required",
        denied: "Denied by policy",
        error: "Execution error",
        failure: "Execution failed",
        functional_failure: "Functional failure",
        product: "Functional failure",
        success: "Completed successfully",
        timeout: "Timed out",
        unknown: "Failure pending confirmation",
    },
    "zh-CN": {
        blocked: "已阻塞",
        env: "环境异常",
        environment_error: "环境异常",
        gate: "Gate 被阻塞",
        gate_blocked: "Gate 被阻塞",
        manual: "需要人工确认",
        manual_pending: "需要人工确认",
        denied: "被策略拒绝",
        error: "执行异常",
        failure: "执行失败",
        functional_failure: "功能失败",
        product: "功能失败",
        success: "已成功完成",
        timeout: "执行超时",
        unknown: "失败原因待确认",
    },
};
const STAGE_ALIASES = {
    analysis: "discover",
    apply: "execute",
    completed: "done",
    delivery: "release",
    deploy: "release",
    discovering: "discover",
    discovery: "discover",
    done: "done",
    execution: "execute",
    implement: "execute",
    implemented: "execute",
    intake: "intake",
    plan: "plan",
    planning: "plan",
    qa: "verify",
    release: "release",
    released: "release",
    review: "verify",
    reviewed: "verify",
    test: "verify",
    testing: "verify",
    todo: "intake",
    verify: "verify",
};
const STAGE_LABELS_BY_LOCALE = {
    en: {
        discover: "Discovery",
        done: "Done",
        execute: "Execution",
        intake: "Intake",
        plan: "Planning",
        release: "Release",
        verify: "Verification",
    },
    "zh-CN": {
        discover: "发现",
        done: "完成",
        execute: "执行",
        intake: "接单",
        plan: "规划",
        release: "发布",
        verify: "验证",
    },
};
const CTA_BY_STATUS_BY_LOCALE = {
    en: {
        archived: "View archive",
        blocked: "Resolve blocker",
        cancelled: "View details",
        completed: "View result",
        failed: "Review failure and retry",
        healthy: "View details",
        idle: "Start run",
        info: "View details",
        paused: "Resume run",
        pending: "Start run",
        running: "View progress",
    },
    "zh-CN": {
        archived: "查看归档",
        blocked: "处理阻塞",
        cancelled: "查看详情",
        completed: "查看结果",
        failed: "复盘失败并重试",
        healthy: "查看详情",
        idle: "启动运行",
        info: "查看详情",
        paused: "恢复运行",
        pending: "启动运行",
        running: "查看进度",
    },
};
const CTA_BY_STAGE_BY_LOCALE = {
    en: {
        discover: "Refine requirements",
        done: "View result",
        execute: "View progress",
        intake: "Start intake",
        plan: "Confirm plan",
        release: "Start release",
        verify: "Handle review",
    },
    "zh-CN": {
        discover: "补充需求",
        done: "查看结果",
        execute: "查看进度",
        intake: "开始接单",
        plan: "确认方案",
        release: "开始发布",
        verify: "处理审查",
    },
};
const UNKNOWN_LABEL_BY_LOCALE = {
    en: "Unknown",
    "zh-CN": "未知",
};
const UNKNOWN_STAGE_BY_LOCALE = {
    en: "Unknown stage",
    "zh-CN": "未知阶段",
};
const VIEW_DETAILS_BY_LOCALE = {
    en: "View details",
    "zh-CN": "查看详情",
};
const UNCLASSIFIED_BY_LOCALE = {
    en: "Unclassified",
    "zh-CN": "未分类",
};
export function normalizeUiLocale(locale) {
    const token = typeof locale === "string" ? locale.trim().toLowerCase() : "";
    if (token.startsWith("zh")) {
        return "zh-CN";
    }
    return "en";
}
export function formatUiDateTime(value, locale = "en", options) {
    const raw = String(value || "").trim();
    if (!raw || raw === "-") {
        return "-";
    }
    const parsed = new Date(raw);
    if (Number.isNaN(parsed.getTime())) {
        return raw;
    }
    return parsed.toLocaleString(normalizeUiLocale(locale), options);
}
export function toCanonicalToken(value) {
    if (!value)
        return undefined;
    const lower = value.toLowerCase().trim();
    return lower || undefined;
}
export function toCanonicalStatusStrict(status) {
    const token = toCanonicalToken(status);
    if (!token)
        return undefined;
    return STATUS_ALIASES[token];
}
export function toCanonicalStatusFuzzy(status) {
    const token = toCanonicalToken(status);
    if (!token)
        return undefined;
    const direct = STATUS_ALIASES[token];
    if (direct)
        return direct;
    if (token.includes("failure")
        || token.includes("failed")
        || token.includes("error")
        || token.includes("timeout")
        || token.includes("reject")
        || token.includes("denied")) {
        return "failed";
    }
    if (token.includes("running") || token.includes("execut") || token.includes("progress") || token.includes("working")) {
        return "running";
    }
    if (token.includes("blocked"))
        return "blocked";
    if (token.includes("pending") || token.includes("waiting"))
        return "pending";
    if (token.includes("paused"))
        return "paused";
    if (token.includes("idle"))
        return "idle";
    if (token.includes("success")
        || token.includes("pass")
        || token.includes("done")
        || token.includes("complete")
        || token.includes("approve")) {
        return "completed";
    }
    return undefined;
}
export function toCanonicalStage(stage) {
    const token = toCanonicalToken(stage);
    if (!token)
        return undefined;
    return STAGE_ALIASES[token];
}
export function knownOutcomeTypeLabel(outcomeType, locale = "en") {
    const token = toCanonicalToken(outcomeType);
    if (!token)
        return undefined;
    return OUTCOME_TYPE_LABELS_BY_LOCALE[normalizeUiLocale(locale)][token];
}
export function knownOutcomeTypeLabelZh(outcomeType) {
    return knownOutcomeTypeLabel(outcomeType, "en");
}
export function outcomeTypeLabel(outcomeType, locale = "en") {
    const resolvedLocale = normalizeUiLocale(locale);
    return knownOutcomeTypeLabel(outcomeType, resolvedLocale) || UNCLASSIFIED_BY_LOCALE[resolvedLocale];
}
export function outcomeTypeLabelZh(outcomeType) {
    return outcomeTypeLabel(outcomeType, "en");
}
export function statusLabelFromCanonical(canonical, locale = "en") {
    const resolvedLocale = normalizeUiLocale(locale);
    if (!canonical)
        return UNKNOWN_LABEL_BY_LOCALE[resolvedLocale];
    return STATUS_LABELS_BY_LOCALE[resolvedLocale][canonical] || UNKNOWN_LABEL_BY_LOCALE[resolvedLocale];
}
export function statusLabelZhFromCanonical(canonical) {
    return statusLabelFromCanonical(canonical, "en");
}
export function statusVariantFromCanonical(canonical) {
    if (canonical === "completed" || canonical === "healthy")
        return "success";
    if (canonical === "failed" || canonical === "cancelled")
        return "failed";
    if (canonical === "running")
        return "running";
    if (canonical === "blocked" || canonical === "pending" || canonical === "paused" || canonical === "idle")
        return "warning";
    return "default";
}
export function statusDotClassFromVariant(variant) {
    if (variant === "success")
        return "status-dot status-dot--success";
    if (variant === "failed")
        return "status-dot status-dot--danger";
    if (variant === "running")
        return "status-dot status-dot--primary";
    if (variant === "warning")
        return "status-dot status-dot--warning";
    return "status-dot";
}
export function badgeClassFromVariant(variant) {
    if (variant === "success")
        return "badge badge--success";
    if (variant === "failed")
        return "badge badge--failed";
    if (variant === "running")
        return "badge badge--running";
    if (variant === "warning")
        return "badge badge--warning";
    return "badge";
}
export function stageLabelFromCanonical(canonical, locale = "en") {
    const resolvedLocale = normalizeUiLocale(locale);
    if (!canonical)
        return UNKNOWN_STAGE_BY_LOCALE[resolvedLocale];
    return STAGE_LABELS_BY_LOCALE[resolvedLocale][canonical] || UNKNOWN_STAGE_BY_LOCALE[resolvedLocale];
}
export function stageLabelZhFromCanonical(canonical) {
    return stageLabelFromCanonical(canonical, "en");
}
export function stageVariantFromCanonical(canonical) {
    if (canonical === "intake" || canonical === "plan")
        return "todo";
    if (canonical === "discover" || canonical === "execute")
        return "active";
    if (canonical === "verify" || canonical === "release")
        return "verify";
    if (canonical === "done")
        return "done";
    return "default";
}
export function statusCtaFromCanonical(canonical, locale = "en") {
    const resolvedLocale = normalizeUiLocale(locale);
    if (!canonical)
        return VIEW_DETAILS_BY_LOCALE[resolvedLocale];
    return CTA_BY_STATUS_BY_LOCALE[resolvedLocale][canonical] || VIEW_DETAILS_BY_LOCALE[resolvedLocale];
}
export function statusCtaZhFromCanonical(canonical) {
    return statusCtaFromCanonical(canonical, "en");
}
export function stageCtaFromCanonical(canonical, locale = "en") {
    const resolvedLocale = normalizeUiLocale(locale);
    if (!canonical)
        return VIEW_DETAILS_BY_LOCALE[resolvedLocale];
    return CTA_BY_STAGE_BY_LOCALE[resolvedLocale][canonical] || VIEW_DETAILS_BY_LOCALE[resolvedLocale];
}
export function stageCtaZhFromCanonical(canonical) {
    return stageCtaFromCanonical(canonical, "en");
}
