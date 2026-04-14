export type UiLocale = "en" | "zh-CN";

export const UI_LOCALE_STORAGE_KEY = "openvibecoding.ui.locale";
export const DEFAULT_UI_LOCALE: UiLocale = "en";
export const UI_LOCALE_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365;

export function normalizeUiLocale(value: string | null | undefined): UiLocale {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized.startsWith("zh")) {
    return "zh-CN";
  }
  return "en";
}

export function detectPreferredUiLocale(): UiLocale {
  if (typeof window !== "undefined") {
    const stored = window.localStorage.getItem(UI_LOCALE_STORAGE_KEY);
    if (stored) {
      return normalizeUiLocale(stored);
    }
    const [browserLanguage] = Array.isArray(window.navigator.languages)
      ? window.navigator.languages
      : [];
    return normalizeUiLocale(browserLanguage || window.navigator.language);
  }
  return DEFAULT_UI_LOCALE;
}

export function readPreferredUiLocaleCookie(cookieHeader: string | null | undefined): UiLocale {
  const rawHeader = String(cookieHeader || "").trim();
  if (!rawHeader) {
    return DEFAULT_UI_LOCALE;
  }
  const segments = rawHeader.split(";").map((segment) => segment.trim());
  for (const segment of segments) {
    if (!segment.startsWith(`${UI_LOCALE_STORAGE_KEY}=`)) {
      continue;
    }
    return normalizeUiLocale(segment.slice(UI_LOCALE_STORAGE_KEY.length + 1));
  }
  return DEFAULT_UI_LOCALE;
}

export function persistPreferredUiLocale(locale: UiLocale): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(UI_LOCALE_STORAGE_KEY, locale);
  document.cookie =
    `${UI_LOCALE_STORAGE_KEY}=${locale}; Path=/; Max-Age=${UI_LOCALE_COOKIE_MAX_AGE_SECONDS}; SameSite=Lax`;
}

export function toggleUiLocale(locale: UiLocale): UiLocale {
  return locale === "en" ? "zh-CN" : "en";
}
