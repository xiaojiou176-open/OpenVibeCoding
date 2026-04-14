import { cookies } from "next/headers";
import { DEFAULT_UI_LOCALE, getUiCopy, type UiCopy, type UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@openvibecoding/frontend-shared/uiLocale";

export async function resolveDashboardUiLocale(): Promise<UiLocale> {
  try {
    const cookieStore = await cookies();
    return normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  } catch {
    return DEFAULT_UI_LOCALE;
  }
}

export async function resolveDashboardUiCopy(): Promise<UiCopy> {
  return getUiCopy(await resolveDashboardUiLocale());
}
