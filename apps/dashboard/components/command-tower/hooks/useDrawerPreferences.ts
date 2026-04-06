import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

type UseDrawerPreferencesOptions = {
  collapsedStorageKey: string;
  pinnedStorageKey: string;
  testMode?: boolean;
};

type UseDrawerPreferencesResult = {
  drawerCollapsed: boolean;
  setDrawerCollapsed: Dispatch<SetStateAction<boolean>>;
  drawerPinned: boolean;
  setDrawerPinned: Dispatch<SetStateAction<boolean>>;
};

export function useDrawerPreferences({
  collapsedStorageKey,
  pinnedStorageKey,
  testMode = process.env.NODE_ENV === "test",
}: UseDrawerPreferencesOptions): UseDrawerPreferencesResult {
  const [drawerCollapsed, setDrawerCollapsed] = useState(true);
  const [drawerPinned, setDrawerPinned] = useState(true);

  useEffect(() => {
    if (typeof window === "undefined" || testMode) {
      return;
    }
    const savedCollapsed = window.localStorage.getItem(collapsedStorageKey);
    const savedPinned = window.localStorage.getItem(pinnedStorageKey);
    if (savedCollapsed === "1") {
      setDrawerCollapsed(true);
    }
    if (savedPinned === "0") {
      setDrawerPinned(false);
    }
  }, [collapsedStorageKey, pinnedStorageKey, testMode]);

  useEffect(() => {
    if (typeof window === "undefined" || testMode) {
      return;
    }
    window.localStorage.setItem(collapsedStorageKey, drawerCollapsed ? "1" : "0");
  }, [collapsedStorageKey, drawerCollapsed, testMode]);

  useEffect(() => {
    if (typeof window === "undefined" || testMode) {
      return;
    }
    window.localStorage.setItem(pinnedStorageKey, drawerPinned ? "1" : "0");
  }, [drawerPinned, pinnedStorageKey, testMode]);

  return {
    drawerCollapsed,
    setDrawerCollapsed,
    drawerPinned,
    setDrawerPinned,
  };
}
