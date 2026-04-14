"use client";

import { createContext, useContext, useMemo, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { DEFAULT_UI_LOCALE, getUiCopy, type UiCopy, type UiLocale } from "@openvibecoding/frontend-shared/uiCopy";

type DashboardLocaleContextValue = {
  locale: UiLocale;
  setLocale: Dispatch<SetStateAction<UiLocale>>;
  uiCopy: UiCopy;
};

const noopSetLocale: Dispatch<SetStateAction<UiLocale>> = () => undefined;

const DashboardLocaleContext = createContext<DashboardLocaleContextValue>({
  locale: DEFAULT_UI_LOCALE,
  setLocale: noopSetLocale,
  uiCopy: getUiCopy(DEFAULT_UI_LOCALE),
});

type DashboardLocaleProviderProps = {
  children: ReactNode;
  locale: UiLocale;
  setLocale: Dispatch<SetStateAction<UiLocale>>;
};

export function DashboardLocaleProvider({ children, locale, setLocale }: DashboardLocaleProviderProps) {
  const value = useMemo(
    () => ({
      locale,
      setLocale,
      uiCopy: getUiCopy(locale),
    }),
    [locale, setLocale],
  );

  return (
    <DashboardLocaleContext.Provider value={value}>
      {children}
    </DashboardLocaleContext.Provider>
  );
}

export function useDashboardLocale(): DashboardLocaleContextValue {
  return useContext(DashboardLocaleContext);
}
