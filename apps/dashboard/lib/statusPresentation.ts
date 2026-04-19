import {
  badgeClassFromVariant,
  formatUiDateTime,
  type UiLocale,
  normalizeUiLocale,
  stageCtaFromCanonical,
  stageLabelFromCanonical,
  stageVariantFromCanonical,
  statusCtaFromCanonical,
  statusLabelFromCanonical,
  statusDotClassFromVariant,
  statusVariantFromCanonical,
  toCanonicalStage,
  toCanonicalStatusFuzzy,
} from "@openvibecoding/frontend-shared/statusPresentation";

export { knownOutcomeTypeLabelZh, outcomeTypeLabelZh } from "@openvibecoding/frontend-shared/statusPresentation";
export type { UiLocale } from "@openvibecoding/frontend-shared/statusPresentation";

export const DASHBOARD_DEFAULT_LOCALE: UiLocale = "en";

export function statusLabel(status: string | undefined | null, locale: string | undefined | null = DASHBOARD_DEFAULT_LOCALE): string {
  return statusLabelFromCanonical(toCanonicalStatusFuzzy(status), normalizeUiLocale(locale));
}

export function statusLabelDefault(status: string | undefined | null): string {
  return statusLabel(status, DASHBOARD_DEFAULT_LOCALE);
}

export function statusLabelZh(status: string | undefined | null): string {
  return statusLabel(status, "zh-CN");
}

export function statusVariant(status: string | undefined | null) {
  return statusVariantFromCanonical(toCanonicalStatusFuzzy(status));
}

export function statusDotClass(status: string | undefined | null): string {
  return statusDotClassFromVariant(statusVariant(status));
}

export function badgeClass(status: string | undefined | null): string {
  return badgeClassFromVariant(statusVariant(status));
}

export function stageLabelZh(stage: string | undefined | null): string {
  return stageLabelFromCanonical(toCanonicalStage(stage), "zh-CN");
}

export function stageVariant(stage: string | undefined | null) {
  return stageVariantFromCanonical(toCanonicalStage(stage));
}

export function statusCtaZh(status: string | undefined | null): string {
  return statusCtaFromCanonical(toCanonicalStatusFuzzy(status), "zh-CN");
}

export function stageCtaZh(stage: string | undefined | null): string {
  return stageCtaFromCanonical(toCanonicalStage(stage), "zh-CN");
}

export function formatDashboardDateTime(
  value: string | undefined | null,
  locale: string | undefined | null = DASHBOARD_DEFAULT_LOCALE,
  options?: Intl.DateTimeFormatOptions,
): string {
  return formatUiDateTime(value, locale, options);
}
