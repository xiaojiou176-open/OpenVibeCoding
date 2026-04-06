type ThemeMode = "light" | "dark";

/**
 * Desktop token initializer.
 *
 * The design tokens are now defined directly in styles.css using :root and
 * @media (prefers-color-scheme: dark), matching the Dashboard's approach.
 *
 * This function only sets the data-theme attribute and color-scheme property
 * so existing components that read data-theme keep working.
 */

function applyTheme(mode: ThemeMode) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.dataset.theme = mode;
  root.style.colorScheme = mode;
}

function resolveThemeMode(): ThemeMode {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function initDesktopTokens() {
  if (typeof window === "undefined") return;

  const media = window.matchMedia("(prefers-color-scheme: dark)");
  applyTheme(resolveThemeMode());

  media.addEventListener("change", (event: MediaQueryListEvent) => {
    applyTheme(event.matches ? "dark" : "light");
  });
}
