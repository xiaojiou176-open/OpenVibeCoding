"use client";

import { useEffect } from "react";

type UsePersistedWorkspaceBindingsParams = {
  workspacePath: string;
  repoName: string;
  setWorkspacePath: (value: string) => void;
  setRepoName: (value: string) => void;
};

const PM_WORKSPACE_STORAGE_KEY = "openvibecoding.pm.workspace";
const PM_REPO_STORAGE_KEY = "openvibecoding.pm.repo";

export function usePersistedWorkspaceBindings({
  workspacePath,
  repoName,
  setWorkspacePath,
  setRepoName,
}: UsePersistedWorkspaceBindingsParams): void {
  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const rememberedWorkspace = window.localStorage.getItem(PM_WORKSPACE_STORAGE_KEY) || "apps/dashboard";
    const rememberedRepo = window.localStorage.getItem(PM_REPO_STORAGE_KEY) || "openvibecoding";
    setWorkspacePath(rememberedWorkspace);
    setRepoName(rememberedRepo);
  }, [setWorkspacePath, setRepoName]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    if (workspacePath.trim()) {
      window.localStorage.setItem(PM_WORKSPACE_STORAGE_KEY, workspacePath.trim());
    }
  }, [workspacePath]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    if (repoName.trim()) {
      window.localStorage.setItem(PM_REPO_STORAGE_KEY, repoName.trim());
    }
  }, [repoName]);
}
