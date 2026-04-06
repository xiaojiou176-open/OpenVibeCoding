import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

import type { PmSessionStatus } from "../../../lib/types";
import {
  FOCUS_OPTIONS,
  SORT_OPTIONS,
  STATUS_OPTIONS,
} from "../commandTowerHomeHelpers";
import type { FocusMode, SortMode } from "../commandTowerHomeHelpers";

type UseCommandTowerHomeFiltersResult = {
  draftStatuses: PmSessionStatus[];
  setDraftStatuses: Dispatch<SetStateAction<PmSessionStatus[]>>;
  draftProjectKey: string;
  setDraftProjectKey: Dispatch<SetStateAction<string>>;
  draftSort: SortMode;
  setDraftSort: Dispatch<SetStateAction<SortMode>>;
  focusMode: FocusMode;
  setFocusMode: Dispatch<SetStateAction<FocusMode>>;
  liveEnabled: boolean;
  setLiveEnabled: Dispatch<SetStateAction<boolean>>;
  appliedStatuses: PmSessionStatus[];
  appliedProjectKey: string;
  appliedSort: SortMode;
  refreshToken: number;
  toggleDraftStatus: (status: PmSessionStatus) => void;
  applyFilters: () => void;
  resetFilters: () => void;
  requestRefresh: () => void;
  buildShareUrl: () => string;
};

export function useCommandTowerHomeFilters(): UseCommandTowerHomeFiltersResult {
  const [draftStatuses, setDraftStatuses] = useState<PmSessionStatus[]>([]);
  const [draftProjectKey, setDraftProjectKey] = useState("");
  const [draftSort, setDraftSort] = useState<SortMode>("updated_desc");
  const [focusMode, setFocusMode] = useState<FocusMode>("all");
  const [liveEnabled, setLiveEnabled] = useState(true);

  const [appliedStatuses, setAppliedStatuses] = useState<PmSessionStatus[]>([]);
  const [appliedProjectKey, setAppliedProjectKey] = useState("");
  const [appliedSort, setAppliedSort] = useState<SortMode>("updated_desc");
  const [refreshToken, setRefreshToken] = useState(0);

  const urlSyncedRef = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined" || urlSyncedRef.current) {
      return;
    }
    urlSyncedRef.current = true;

    const params = new URLSearchParams(window.location.search);
    const mergedStatusValues = [...params.getAll("status[]"), ...params.getAll("status")];
    const nextStatuses = Array.from(
      new Set(
        mergedStatusValues.filter((value): value is PmSessionStatus =>
          STATUS_OPTIONS.includes(value as PmSessionStatus),
        ),
      ),
    );

    const nextProjectKey = params.get("project_key")?.trim() || "";
    const rawSort = params.get("sort")?.trim() || "";
    const nextSort: SortMode = SORT_OPTIONS.some((item) => item.value === rawSort)
      ? (rawSort as SortMode)
      : "updated_desc";
    const rawFocus = params.get("focus")?.trim() || "";
    const nextFocus: FocusMode = FOCUS_OPTIONS.some((item) => item.value === rawFocus)
      ? (rawFocus as FocusMode)
      : "all";
    const rawLive = params.get("live")?.trim();
    const nextLiveEnabled = rawLive === "0" ? false : true;

    setDraftStatuses(nextStatuses);
    setAppliedStatuses(nextStatuses);
    setDraftProjectKey(nextProjectKey);
    setAppliedProjectKey(nextProjectKey);
    setDraftSort(nextSort);
    setAppliedSort(nextSort);
    setFocusMode(nextFocus);
    setLiveEnabled(nextLiveEnabled);

    if (
      nextStatuses.length > 0 ||
      nextProjectKey ||
      nextSort !== "updated_desc" ||
      nextFocus !== "all" ||
      !nextLiveEnabled
    ) {
      setRefreshToken((prev) => prev + 1);
    }
  }, []);

  const toggleDraftStatus = useCallback((status: PmSessionStatus) => {
    setDraftStatuses((prev) => {
      if (prev.includes(status)) {
        return prev.filter((item) => item !== status);
      }
      return [...prev, status];
    });
  }, []);

  const applyFilters = useCallback(() => {
    setAppliedStatuses(draftStatuses);
    setAppliedProjectKey(draftProjectKey.trim());
    setAppliedSort(draftSort);
    setRefreshToken((prev) => prev + 1);
  }, [draftProjectKey, draftSort, draftStatuses]);

  const resetFilters = useCallback(() => {
    setDraftStatuses([]);
    setDraftProjectKey("");
    setDraftSort("updated_desc");
    setAppliedStatuses([]);
    setAppliedProjectKey("");
    setAppliedSort("updated_desc");
    setRefreshToken((prev) => prev + 1);
  }, []);

  const requestRefresh = useCallback(() => {
    setRefreshToken((prev) => prev + 1);
  }, []);

  const buildShareUrl = useCallback(() => {
    if (typeof window === "undefined") {
      return "";
    }
    const url = new URL(window.location.href);
    url.search = "";
    for (const status of appliedStatuses) {
      url.searchParams.append("status[]", status);
    }
    if (appliedProjectKey) {
      url.searchParams.set("project_key", appliedProjectKey);
    }
    url.searchParams.set("sort", appliedSort);
    url.searchParams.set("focus", focusMode);
    url.searchParams.set("live", liveEnabled ? "1" : "0");
    return url.toString();
  }, [appliedProjectKey, appliedSort, appliedStatuses, focusMode, liveEnabled]);

  return {
    draftStatuses,
    setDraftStatuses,
    draftProjectKey,
    setDraftProjectKey,
    draftSort,
    setDraftSort,
    focusMode,
    setFocusMode,
    liveEnabled,
    setLiveEnabled,
    appliedStatuses,
    appliedProjectKey,
    appliedSort,
    refreshToken,
    toggleDraftStatus,
    applyFilters,
    resetFilters,
    requestRefresh,
    buildShareUrl,
  };
}
