import {
  badgeClassFromVariant,
  formatUiDateTime,
  type StatusVariant,
  type UiLocale,
  stageCtaFromCanonical,
  stageLabelFromCanonical,
  stageVariantFromCanonical,
  statusCtaFromCanonical,
  statusLabelFromCanonical,
  statusDotClassFromVariant,
  statusVariantFromCanonical,
  toCanonicalStage,
  toCanonicalStatusStrict,
  toCanonicalToken,
} from "@openvibecoding/frontend-shared/statusPresentation";

export type RunOutcomeSemantic = "gate_blocked" | "environment_error" | "manual_pending" | "functional_failure" | "unknown";
export const DESKTOP_DEFAULT_LOCALE: UiLocale = "en";

const CJK_PATTERN = /[\u3400-\u9fff]/u;

function normalizeFailureCode(failureCode: string | undefined | null): string {
  return toCanonicalToken(failureCode) || "";
}

function toPublicCopy(explicitValue: string | undefined | null): string | undefined {
  const explicit = typeof explicitValue === "string" ? explicitValue.trim() : "";
  if (!explicit || CJK_PATTERN.test(explicit)) return undefined;
  return explicit;
}

function toDesktopBadgeClassContract(raw: string): string {
  return raw
    .split(/\s+/)
    .filter(Boolean)
    .map((token) => {
      if (token === "badge") return "ui-badge";
      if (token.startsWith("badge--")) return `ui-badge--${token.slice("badge--".length)}`;
      return token;
    })
    .join(" ");
}

export function outcomeSemantic(
  outcomeType: string | undefined | null,
  status: string | undefined | null,
  failureClass?: string | undefined | null,
  failureCode?: string | undefined | null,
): RunOutcomeSemantic {
  const outcomeToken = toCanonicalToken(outcomeType);
  const statusToken = toCanonicalStatusStrict(status);
  const classToken = toCanonicalToken(failureClass);
  const codeToken = normalizeFailureCode(failureCode);

  if (classToken === "gate") return "gate_blocked";
  if (classToken === "manual") return "manual_pending";
  if (classToken === "env") return "environment_error";
  if (classToken === "product") return "functional_failure";

  if (outcomeToken && (outcomeToken.includes("gate") || outcomeToken.includes("blocked") || outcomeToken.includes("deny"))) {
    return "gate_blocked";
  }
  if (outcomeToken && (outcomeToken.includes("manual") || outcomeToken.includes("approval") || outcomeToken.includes("human"))) {
    return "manual_pending";
  }
  if (outcomeToken && (outcomeToken.includes("env") || outcomeToken.includes("infra") || outcomeToken.includes("runtime"))) {
    return "environment_error";
  }
  if (outcomeToken && (outcomeToken.includes("functional") || outcomeToken.includes("biz") || outcomeToken.includes("logic"))) {
    return "functional_failure";
  }

  if (codeToken.startsWith("gate_") || codeToken.includes("diff_gate") || codeToken.startsWith("policy_")) {
    return "gate_blocked";
  }
  if (codeToken.startsWith("approval_") || codeToken.startsWith("human_")) return "manual_pending";
  if (
    codeToken.startsWith("env_")
    || codeToken.startsWith("infra_")
    || codeToken.startsWith("runtime_")
    || codeToken.startsWith("rollback_")
  ) {
    return "environment_error";
  }
  if (codeToken.startsWith("func_") || codeToken.startsWith("biz_") || codeToken.startsWith("logic_")) return "functional_failure";

  if (statusToken === "blocked" || statusToken === "paused" || statusToken === "pending") return "manual_pending";
  if (statusToken === "failed") return "functional_failure";
  return "unknown";
}

export function outcomeSemanticLabelZh(
  outcomeType: string | undefined | null,
  outcomeLabelZh: string | undefined | null,
  status: string | undefined | null,
  failureClass?: string | undefined | null,
  failureCode?: string | undefined | null,
): string {
  return outcomeSemanticLabel(
    outcomeType,
    outcomeLabelZh,
    status,
    DESKTOP_DEFAULT_LOCALE,
    failureClass,
    failureCode,
  );
}

export function outcomeSemanticLabel(
  outcomeType: string | undefined | null,
  outcomeLabel: string | undefined | null,
  status: string | undefined | null,
  locale: UiLocale = DESKTOP_DEFAULT_LOCALE,
  failureClass?: string | undefined | null,
  failureCode?: string | undefined | null,
): string {
  const resolvedLocale = locale || DESKTOP_DEFAULT_LOCALE;
  const explicit = typeof outcomeLabel === "string" ? outcomeLabel.trim() : "";
  if (explicit) {
    if (resolvedLocale === "zh-CN" || !CJK_PATTERN.test(explicit)) {
      return explicit;
    }
  }

  const semantic = outcomeSemantic(outcomeType, status, failureClass, failureCode);
  if (resolvedLocale === "zh-CN") {
    if (semantic === "gate_blocked") return "Gate 被阻塞";
    if (semantic === "environment_error") return "环境异常";
    if (semantic === "manual_pending") return "需要人工确认";
    if (semantic === "functional_failure") return "功能失败";
    return "状态待确认";
  }
  if (semantic === "gate_blocked") return "Gate blocked";
  if (semantic === "environment_error") return "Environment issue";
  if (semantic === "manual_pending") return "Manual confirmation required";
  if (semantic === "functional_failure") return "Functional failure";
  return "Status pending confirmation";
}

export function outcomeSemanticBadgeClass(
  outcomeType: string | undefined | null,
  status: string | undefined | null,
  failureClass?: string | undefined | null,
  failureCode?: string | undefined | null,
): string {
  return toDesktopBadgeClassContract(badgeClassFromVariant(
    outcomeSemanticBadgeVariant(outcomeType, status, failureClass, failureCode),
  ));
}

export function outcomeSemanticBadgeVariant(
  outcomeType: string | undefined | null,
  status: string | undefined | null,
  failureClass?: string | undefined | null,
  failureCode?: string | undefined | null,
): StatusVariant {
  const semantic = outcomeSemantic(outcomeType, status, failureClass, failureCode);
  if (semantic === "gate_blocked" || semantic === "manual_pending") return "warning";
  if (semantic === "environment_error" || semantic === "functional_failure") return "failed";
  return badgeVariant(status);
}

export function outcomeActionHintZh(
  actionHintZh: string | undefined | null,
  outcomeType: string | undefined | null,
  status: string | undefined | null,
  failureClass?: string | undefined | null,
  failureCode?: string | undefined | null,
): string {
  return outcomeActionHint(
    actionHintZh,
    outcomeType,
    status,
    DESKTOP_DEFAULT_LOCALE,
    failureClass,
    failureCode,
  );
}

export function outcomeActionHint(
  actionHint: string | undefined | null,
  outcomeType: string | undefined | null,
  status: string | undefined | null,
  locale: UiLocale = DESKTOP_DEFAULT_LOCALE,
  failureClass?: string | undefined | null,
  failureCode?: string | undefined | null,
): string {
  const resolvedLocale = locale || DESKTOP_DEFAULT_LOCALE;
  const explicit = typeof actionHint === "string" ? actionHint.trim() : "";
  if (explicit) {
    if (resolvedLocale === "zh-CN" || !CJK_PATTERN.test(explicit)) {
      return explicit;
    }
  }
  const semantic = outcomeSemantic(outcomeType, status, failureClass, failureCode);
  if (resolvedLocale === "zh-CN") {
    if (semantic === "gate_blocked") return "先处理 Gate，再重试。";
    if (semantic === "environment_error") return "先检查环境和依赖，再重试。";
    if (semantic === "manual_pending") return "先完成人工确认，再继续。";
    if (semantic === "functional_failure") return "先修复功能问题，再重试。";
    return "先查看详情，再继续排查。";
  }
  if (semantic === "gate_blocked") return "Adjust the gate and retry";
  if (semantic === "environment_error") return "Check the environment and dependencies, then retry";
  if (semantic === "manual_pending") return "Complete manual confirmation before continuing";
  if (semantic === "functional_failure") return "Fix the functional issue and retry";
  return "View details and continue investigating";
}

export function statusLabelZh(status: string | undefined | null): string {
  return statusLabelDesktop(status, DESKTOP_DEFAULT_LOCALE);
}

export function statusLabelDesktop(
  status: string | undefined | null,
  locale: UiLocale = DESKTOP_DEFAULT_LOCALE,
): string {
  return statusLabelFromCanonical(toCanonicalStatusStrict(status), locale);
}

export function statusVariant(status: string | undefined | null) {
  return statusVariantFromCanonical(toCanonicalStatusStrict(status));
}

export function statusDotClass(status: string | undefined | null): string {
  return statusDotClassFromVariant(statusVariant(status));
}

export function badgeVariant(status: string | undefined | null): StatusVariant {
  return statusVariant(status);
}

export function badgeClass(status: string | undefined | null): string {
  return toDesktopBadgeClassContract(badgeClassFromVariant(badgeVariant(status)));
}

export function stageLabelZh(stage: string | undefined | null): string {
  return stageLabelFromCanonical(toCanonicalStage(stage), DESKTOP_DEFAULT_LOCALE);
}

export function stageVariant(stage: string | undefined | null) {
  return stageVariantFromCanonical(toCanonicalStage(stage));
}

export function statusCtaZh(status: string | undefined | null): string {
  return statusCtaFromCanonical(toCanonicalStatusStrict(status), DESKTOP_DEFAULT_LOCALE);
}

export function stageCtaZh(stage: string | undefined | null): string {
  return stageCtaFromCanonical(toCanonicalStage(stage), DESKTOP_DEFAULT_LOCALE);
}

export function formatDesktopDateTime(
  value: string | undefined | null,
  locale: string | undefined | null = DESKTOP_DEFAULT_LOCALE,
  options?: Intl.DateTimeFormatOptions,
): string {
  return formatUiDateTime(value, locale, options);
}
