"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { useDashboardLocale } from "../DashboardLocaleContext";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader } from "../ui/card";
import { Input, Select } from "../ui/input";
import {
  applyRoleConfig,
  fetchRoleConfig,
  mutationExecutionCapability,
  previewRoleConfig,
} from "../../lib/api";
import { localizeRolePurpose } from "../../lib/rolePresentation";
import type {
  JsonValue,
  RoleCatalogRecord,
  RoleConfigApplyResponse,
  RoleConfigPreviewResponse,
  RoleConfigSurface,
} from "../../lib/types";

type RoleConfigControlPlaneProps = {
  roleCatalog: RoleCatalogRecord[];
};

type RoleConfigDraft = {
  system_prompt_ref: string;
  skills_bundle_ref: string;
  mcp_bundle_ref: string;
  runtime_binding: {
    runner: string;
    provider: string;
    model: string;
  };
};

type RoleConfigCopy = {
  summaryTitle: string;
  summaryHint: string;
  title: string;
  subtitle: string;
  badgeApplyEnabled: (role: string | null | undefined) => string;
  badgePreviewOnly: string;
  emptyTitle: string;
  emptySubtitle: string;
  noRolePurpose: string;
  formTitle: string;
  formSubtitle: string;
  roleLabel: string;
  purposeLabel: string;
  loading: string;
  promptRefLabel: string;
  skillsBundleLabel: string;
  mcpBundleLabel: string;
  runtimeRunnerLabel: string;
  runtimeProviderLabel: string;
  runtimeModelLabel: string;
  runnerInherit: string;
  previewButton: string;
  previewingButton: string;
  applyButton: string;
  applyingButton: string;
  previewOnlyReason: string;
  fieldModeNote: string;
  successSaved: (role: string) => string;
  currentSurfaceTitle: string;
  previewSurfaceTitle: string;
  previewCardTitle: string;
  previewCardSubtitleReady: string;
  previewCardSubtitleBlocked: string;
  previewNoChanges: string;
  summaryStatus: (surface: RoleConfigSurface) => string;
  executionAuthorityLabel: string;
  persistedSourceLabel: string;
  persistedSourceNote: string;
  runtimeCapabilityTitle: string;
  capabilityLaneLabel: string;
  compatApiModeLabel: string;
  providerStatusLabel: string;
  toolExecutionLabel: string;
  notesLabel: string;
  notSetLabel: string;
  fieldLabels: Record<string, string>;
};

function getRoleConfigCopy(locale: "en" | "zh-CN"): RoleConfigCopy {
  if (locale === "zh-CN") {
    return {
      summaryTitle: "高级：角色行为配置",
      summaryHint: "只在你真的要改仓库级角色默认值时再展开。已经在跑的任务仍然以 task_contract 为准。",
      title: "角色行为配置",
      subtitle: "先看角色目的，再决定要不要改高级默认值。这里改的是仓库级默认行为，不是当前正在执行的任务合约。",
      badgeApplyEnabled: (role) => `可保存：${role || "已授权"}`,
      badgePreviewOnly: "仅可预览",
      emptyTitle: "暂时没有可配置的角色",
      emptySubtitle: "当前还没有注册角色，所以这里还不能展开配置面板。",
      noRolePurpose: "当前还没有发布这个角色的目的说明。",
      formTitle: "可编辑角色默认值",
      formSubtitle: "这里只改四类高级默认值：系统提示词来源、技能包、MCP 工具包和运行时绑定。",
      roleLabel: "角色",
      purposeLabel: "角色目的",
      loading: "正在读取角色配置...",
      promptRefLabel: "系统提示词来源",
      skillsBundleLabel: "技能包来源",
      mcpBundleLabel: "MCP 工具包来源",
      runtimeRunnerLabel: "运行器",
      runtimeProviderLabel: "运行时提供方",
      runtimeModelLabel: "运行时模型",
      runnerInherit: "继承 / 待解析",
      previewButton: "预览生效结果",
      previewingButton: "预览中...",
      applyButton: "保存仓库默认值",
      applyingButton: "保存中...",
      previewOnlyReason: "当前只能做预览；如果要真正保存仓库默认值，需要具备可执行的操作角色。",
      fieldModeNote: "这里不会改角色目的，也不会改 task_contract 的执行权。首屏目录和读模型仍然保持派生只读。",
      successSaved: (role) => `已保存 ${role} 的仓库默认值。`,
      currentSurfaceTitle: "当前生效行为",
      previewSurfaceTitle: "预览后的生效行为",
      previewCardTitle: "变更预览",
      previewCardSubtitleReady: "预览已通过 fail-closed 校验",
      previewCardSubtitleBlocked: "预览被阻止",
      previewNoChanges: "这次预览和当前生效默认值相比没有变化。",
      summaryStatus: (surface) => `${surface.authority} / ${surface.overlay_state} / ${surface.validation}`,
      executionAuthorityLabel: "执行权",
      persistedSourceLabel: "落盘来源",
      persistedSourceNote: "这只会更新未来编译出来的角色默认值。已经在跑的任务，仍然跟随当前 task_contract。",
      runtimeCapabilityTitle: "运行时能力明细",
      capabilityLaneLabel: "能力通道",
      compatApiModeLabel: "兼容 API 模式",
      providerStatusLabel: "提供方状态",
      toolExecutionLabel: "工具执行",
      notesLabel: "补充说明",
      notSetLabel: "未设置",
      fieldLabels: {
        system_prompt_ref: "系统提示词来源",
        skills_bundle_ref: "技能包来源",
        mcp_bundle_ref: "MCP 工具包来源",
        "runtime_binding.runner": "运行器",
        "runtime_binding.provider": "运行时提供方",
        "runtime_binding.model": "运行时模型",
      },
    };
  }

  return {
    summaryTitle: "Role behavior settings (advanced)",
    summaryHint: "Open this only when you intentionally want to change repo-owned role defaults. Running tasks still obey the active task_contract.",
    title: "Role behavior settings",
    subtitle: "Start from the role purpose, then decide whether you actually need to change advanced repo-owned defaults. This does not rewrite the currently running task contract.",
    badgeApplyEnabled: (role) => `Apply enabled for ${role || "operator"}`,
    badgePreviewOnly: "Preview only",
    emptyTitle: "No configurable roles yet",
    emptySubtitle: "No roles are registered yet, so this advanced panel cannot hydrate a config form.",
    noRolePurpose: "No role purpose has been published yet.",
    formTitle: "Editable role defaults",
    formSubtitle: "This advanced panel edits four repo-owned defaults only: prompt source, skills bundle, MCP bundle, and runtime binding.",
    roleLabel: "Role",
    purposeLabel: "Role purpose",
    loading: "Loading role configuration...",
    promptRefLabel: "System prompt source",
    skillsBundleLabel: "Skills bundle source",
    mcpBundleLabel: "MCP bundle source",
    runtimeRunnerLabel: "Runtime runner",
    runtimeProviderLabel: "Runtime provider",
    runtimeModelLabel: "Runtime model",
    runnerInherit: "Inherit / unresolved",
    previewButton: "Preview effective result",
    previewingButton: "Previewing...",
    applyButton: "Save repo defaults",
    applyingButton: "Saving...",
    previewOnlyReason: "Preview is available, but saving repo defaults still requires an executable operator role.",
    fieldModeNote: "This panel does not change role purpose or the task_contract execution authority. Read models and catalog surfaces stay derived.",
    successSaved: (role) => `Saved repo-owned defaults for ${role}.`,
    currentSurfaceTitle: "Current effective behavior",
    previewSurfaceTitle: "Previewed effective behavior",
    previewCardTitle: "Change preview",
    previewCardSubtitleReady: "Preview passed fail-closed validation",
    previewCardSubtitleBlocked: "Preview blocked",
    previewNoChanges: "The preview matches the current effective defaults.",
    summaryStatus: (surface) => `${surface.authority} / ${surface.overlay_state} / ${surface.validation}`,
    executionAuthorityLabel: "Execution authority",
    persistedSourceLabel: "Persisted source",
    persistedSourceNote: "This only updates future compiled role defaults. Running tasks still follow the active task contract.",
    runtimeCapabilityTitle: "Runtime capability details",
    capabilityLaneLabel: "Capability lane",
    compatApiModeLabel: "Compat API mode",
    providerStatusLabel: "Provider status",
    toolExecutionLabel: "Tool execution",
    notesLabel: "Notes",
    notSetLabel: "Not set",
    fieldLabels: {
      system_prompt_ref: "System prompt source",
      skills_bundle_ref: "Skills bundle source",
      mcp_bundle_ref: "MCP bundle source",
      "runtime_binding.runner": "Runtime runner",
      "runtime_binding.provider": "Runtime provider",
      "runtime_binding.model": "Runtime model",
    },
  };
}

function createEmptyDraft(): RoleConfigDraft {
  return {
    system_prompt_ref: "",
    skills_bundle_ref: "",
    mcp_bundle_ref: "",
    runtime_binding: {
      runner: "",
      provider: "",
      model: "",
    },
  };
}

function createRunnerOptions(copy: RoleConfigCopy) {
  return [
    { value: "", label: copy.runnerInherit },
    { value: "agents", label: "agents" },
    { value: "app_server", label: "app_server" },
    { value: "codex", label: "codex" },
    { value: "claude", label: "claude" },
  ];
}

function draftFromSurface(surface: RoleConfigSurface | null): RoleConfigDraft {
  if (!surface) {
    return createEmptyDraft();
  }
  const editableNow = surface.editable_now;
  if (!editableNow || typeof editableNow !== "object") {
    return createEmptyDraft();
  }
  const runtimeBinding =
    editableNow.runtime_binding && typeof editableNow.runtime_binding === "object"
      ? editableNow.runtime_binding
      : createEmptyDraft().runtime_binding;
  return {
    system_prompt_ref: editableNow.system_prompt_ref || "",
    skills_bundle_ref: editableNow.skills_bundle_ref || "",
    mcp_bundle_ref: editableNow.mcp_bundle_ref || "",
    runtime_binding: {
      runner: runtimeBinding.runner || "",
      provider: runtimeBinding.provider || "",
      model: runtimeBinding.model || "",
    },
  };
}

function payloadFromDraft(draft: RoleConfigDraft): Record<string, JsonValue> {
  const clean = (value: string) => {
    const normalized = value.trim();
    return normalized || null;
  };
  return {
    system_prompt_ref: clean(draft.system_prompt_ref),
    skills_bundle_ref: clean(draft.skills_bundle_ref),
    mcp_bundle_ref: clean(draft.mcp_bundle_ref),
    runtime_binding: {
      runner: clean(draft.runtime_binding.runner),
      provider: clean(draft.runtime_binding.provider),
      model: clean(draft.runtime_binding.model),
    },
  };
}

function readableValue(value: string | null | undefined, emptyLabel: string): string {
  const normalized = String(value || "").trim();
  return normalized || emptyLabel;
}

function editableSurfaceValues(surface: RoleConfigSurface | null | undefined): RoleConfigDraft {
  return draftFromSurface(surface ?? null);
}

function runtimeCapabilitySummary(surface: RoleConfigSurface | null | undefined) {
  const capability = surface?.runtime_capability;
  return {
    lane: capability?.lane || "unknown",
    compatApiMode: capability?.compat_api_mode || "unknown",
    providerStatus: capability?.provider_status || "unresolved",
    toolExecution: capability?.tool_execution || "fail-closed",
    notes: Array.isArray(capability?.notes) ? capability.notes : [],
  };
}

function changeLabel(field: string, copy: RoleConfigCopy): string {
  return copy.fieldLabels[field] || field;
}

function RuntimeCapabilityBlock({ surface, copy }: { surface: RoleConfigSurface; copy: RoleConfigCopy }) {
  const capability = runtimeCapabilitySummary(surface);
  return (
    <div className="data-list">
      <div className="data-list-row">
        <span className="data-list-label">{copy.capabilityLaneLabel}</span>
        <span className="data-list-value mono">{capability.lane}</span>
      </div>
      <div className="data-list-row">
        <span className="data-list-label">{copy.compatApiModeLabel}</span>
        <span className="data-list-value mono">{capability.compatApiMode}</span>
      </div>
      <div className="data-list-row">
        <span className="data-list-label">{copy.providerStatusLabel}</span>
        <span className="data-list-value mono">{capability.providerStatus}</span>
      </div>
      <div className="data-list-row">
        <span className="data-list-label">{copy.toolExecutionLabel}</span>
        <span className="data-list-value mono">{capability.toolExecution}</span>
      </div>
      <div className="data-list-row">
        <span className="data-list-label">{copy.notesLabel}</span>
        <span className="data-list-value">
          <span className="stack-gap-2">
            {capability.notes.length > 0 ? (
              capability.notes.map((note) => (
                <span key={note} className="muted">
                  {note}
                </span>
              ))
            ) : (
              <span className="muted">{copy.notSetLabel}</span>
            )}
          </span>
        </span>
      </div>
    </div>
  );
}

function SurfaceSummary({
  heading,
  surface,
  copy,
}: {
  heading: string;
  surface: RoleConfigSurface;
  copy: RoleConfigCopy;
}) {
  const editableNow = editableSurfaceValues(surface);
  return (
    <Card variant="detail">
      <CardHeader>
        <div className="stack-gap-2">
          <span className="card-header-title">{heading}</span>
          <span className="mono muted">{copy.summaryStatus(surface)}</span>
        </div>
      </CardHeader>
      <CardContent>
        <div className="data-list">
          <div className="data-list-row">
            <span className="data-list-label">{copy.promptRefLabel}</span>
            <span className="data-list-value mono">{readableValue(editableNow.system_prompt_ref, copy.notSetLabel)}</span>
          </div>
          <div className="data-list-row">
            <span className="data-list-label">{copy.skillsBundleLabel}</span>
            <span className="data-list-value mono">{readableValue(editableNow.skills_bundle_ref, copy.notSetLabel)}</span>
          </div>
          <div className="data-list-row">
            <span className="data-list-label">{copy.mcpBundleLabel}</span>
            <span className="data-list-value mono">{readableValue(editableNow.mcp_bundle_ref, copy.notSetLabel)}</span>
          </div>
          <div className="data-list-row">
            <span className="data-list-label">
              {copy.runtimeRunnerLabel} / {copy.runtimeProviderLabel} / {copy.runtimeModelLabel}
            </span>
            <span className="data-list-value mono">
              {readableValue(editableNow.runtime_binding.runner, copy.notSetLabel)} / {readableValue(editableNow.runtime_binding.provider, copy.notSetLabel)} / {readableValue(editableNow.runtime_binding.model, copy.notSetLabel)}
            </span>
          </div>
          <div className="data-list-row">
            <span className="data-list-label">{copy.executionAuthorityLabel}</span>
            <span className="data-list-value">
              <Badge variant="running">{surface.execution_authority}</Badge>
            </span>
          </div>
        </div>
        <div className="stack-gap-2 mt-3">
          <p className="mono muted">
            {copy.persistedSourceLabel}: {surface.persisted_source}
          </p>
          <p className="muted">{copy.persistedSourceNote}</p>
        </div>
        <details className="diff-gate-details mt-3">
          <summary>{copy.runtimeCapabilityTitle}</summary>
          <div className="mt-2">
            <RuntimeCapabilityBlock surface={surface} copy={copy} />
          </div>
        </details>
      </CardContent>
    </Card>
  );
}

export function RoleConfigControlPlane({ roleCatalog }: RoleConfigControlPlaneProps) {
  const { locale } = useDashboardLocale();
  const copy = getRoleConfigCopy(locale);
  const router = useRouter();
  const mutationCapability = mutationExecutionCapability();
  const [selectedRole, setSelectedRole] = useState(roleCatalog[0]?.role || "");
  const [surface, setSurface] = useState<RoleConfigSurface | null>(null);
  const [draft, setDraft] = useState<RoleConfigDraft>(createEmptyDraft());
  const [preview, setPreview] = useState<RoleConfigPreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (!selectedRole) {
      setSurface(null);
      setDraft(createEmptyDraft());
      setPreview(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    void fetchRoleConfig(selectedRole)
      .then((payload) => {
        if (cancelled) return;
        setSurface(payload);
        setDraft(draftFromSurface(payload));
        setPreview(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setSurface(null);
        setPreview(null);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRole]);

  const roleOptions = useMemo(
    () =>
      roleCatalog.map((record) => ({
        role: record.role,
        purpose: localizeRolePurpose(record.role, record.purpose, locale) || copy.noRolePurpose,
      })),
    [copy.noRolePurpose, locale, roleCatalog],
  );

  const runnerOptions = useMemo(() => createRunnerOptions(copy), [copy]);

  const applyDisabledReason = mutationCapability.executable ? "" : copy.previewOnlyReason;

  async function handlePreview() {
    if (!selectedRole) return;
    setPreviewing(true);
    setError("");
    setSuccess("");
    try {
      const payload = await previewRoleConfig(selectedRole, payloadFromDraft(draft));
      setPreview(payload);
    } catch (err) {
      setPreview(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPreviewing(false);
    }
  }

  function handleApply() {
    if (!selectedRole || !mutationCapability.executable) {
      return;
    }
    setApplying(true);
    setError("");
    setSuccess("");
    void applyRoleConfig(selectedRole, payloadFromDraft(draft))
      .then((payload: RoleConfigApplyResponse) => {
        setSurface(payload.surface);
        setDraft(draftFromSurface(payload.surface));
        setPreview(null);
        setSuccess(copy.successSaved(payload.role));
        router.refresh();
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        setApplying(false);
      });
  }

  if (roleOptions.length === 0) {
    return (
      <section className="app-section" aria-labelledby="role-config-control-plane-title">
        <div className="section-header">
          <div>
            <h2 id="role-config-control-plane-title" className="section-title">
              {copy.emptyTitle}
            </h2>
            <p className="mono muted">{copy.emptySubtitle}</p>
          </div>
        </div>
      </section>
    );
  }

  const selectedRolePurpose = roleOptions.find((item) => item.role === selectedRole)?.purpose || copy.noRolePurpose;

  return (
    <section className="app-section" aria-labelledby="role-config-control-plane-title">
      <Card asChild variant="detail">
        <details open={Boolean(preview || error || success)}>
          <summary className="section-title" id="role-config-control-plane-title">
            {copy.summaryTitle}
          </summary>
          <div className="section-header mt-2">
            <div>
              <h2 className="section-title">{copy.title}</h2>
              <p className="page-subtitle">{copy.subtitle}</p>
              <p className="mono muted">{copy.summaryHint}</p>
            </div>
            <Badge variant={mutationCapability.executable ? "success" : "warning"}>
              {mutationCapability.executable
                ? copy.badgeApplyEnabled(mutationCapability.operatorRole)
                : copy.badgePreviewOnly}
            </Badge>
          </div>

          <div className="grid-2 mt-3">
            <Card variant="detail">
              <CardHeader>
                <div className="stack-gap-2">
                  <span className="card-header-title">{copy.formTitle}</span>
                  <span className="muted">{copy.formSubtitle}</span>
                </div>
              </CardHeader>
              <CardContent>
                <div className="stack-gap-2">
                  <label className="stack-gap-2">
                    <span className="muted">{copy.roleLabel}</span>
                    <Select
                      aria-label={copy.roleLabel}
                      value={selectedRole}
                      onChange={(event) => {
                        setSelectedRole(event.target.value);
                        setSuccess("");
                        setError("");
                      }}
                    >
                      {roleOptions.map((item) => (
                        <option key={item.role} value={item.role}>
                          {item.role}
                        </option>
                      ))}
                    </Select>
                  </label>
                  <div className="stack-gap-2">
                    <span className="muted">{copy.purposeLabel}</span>
                    <p className="muted">{selectedRolePurpose}</p>
                  </div>
                </div>

                {loading ? (
                  <p className="mono muted">{copy.loading}</p>
                ) : (
                  <div className="stack-gap-2 mt-3">
                    <label className="stack-gap-2">
                      <span className="muted">{copy.promptRefLabel}</span>
                      <Input
                        aria-label={copy.promptRefLabel}
                        value={draft.system_prompt_ref}
                        onChange={(event) => setDraft((current) => ({ ...current, system_prompt_ref: event.target.value }))}
                      />
                    </label>
                    <label className="stack-gap-2">
                      <span className="muted">{copy.skillsBundleLabel}</span>
                      <Input
                        aria-label={copy.skillsBundleLabel}
                        value={draft.skills_bundle_ref}
                        onChange={(event) => setDraft((current) => ({ ...current, skills_bundle_ref: event.target.value }))}
                      />
                    </label>
                    <label className="stack-gap-2">
                      <span className="muted">{copy.mcpBundleLabel}</span>
                      <Input
                        aria-label={copy.mcpBundleLabel}
                        value={draft.mcp_bundle_ref}
                        onChange={(event) => setDraft((current) => ({ ...current, mcp_bundle_ref: event.target.value }))}
                      />
                    </label>
                    <div className="grid-2">
                      <label className="stack-gap-2">
                        <span className="muted">{copy.runtimeRunnerLabel}</span>
                        <Select
                          aria-label={copy.runtimeRunnerLabel}
                          value={draft.runtime_binding.runner}
                          onChange={(event) =>
                            setDraft((current) => ({
                              ...current,
                              runtime_binding: { ...current.runtime_binding, runner: event.target.value },
                            }))
                          }
                        >
                          {runnerOptions.map((item) => (
                            <option key={item.value || "empty"} value={item.value}>
                              {item.label}
                            </option>
                          ))}
                        </Select>
                      </label>
                      <label className="stack-gap-2">
                        <span className="muted">{copy.runtimeProviderLabel}</span>
                        <Input
                          aria-label={copy.runtimeProviderLabel}
                          value={draft.runtime_binding.provider}
                          onChange={(event) =>
                            setDraft((current) => ({
                              ...current,
                              runtime_binding: { ...current.runtime_binding, provider: event.target.value },
                            }))
                          }
                        />
                      </label>
                    </div>
                    <label className="stack-gap-2">
                      <span className="muted">{copy.runtimeModelLabel}</span>
                      <Input
                        aria-label={copy.runtimeModelLabel}
                        value={draft.runtime_binding.model}
                        onChange={(event) =>
                          setDraft((current) => ({
                            ...current,
                            runtime_binding: { ...current.runtime_binding, model: event.target.value },
                          }))
                        }
                      />
                    </label>
                    <div className="toolbar toolbar--mt">
                      <Button onClick={() => void handlePreview()} disabled={!selectedRole || previewing || loading}>
                        {previewing ? copy.previewingButton : copy.previewButton}
                      </Button>
                      <Button onClick={handleApply} disabled={!selectedRole || applying || !mutationCapability.executable}>
                        {applying ? copy.applyingButton : copy.applyButton}
                      </Button>
                    </div>
                    {applyDisabledReason ? <p className="mono muted">{applyDisabledReason}</p> : null}
                    {error ? (
                      <p className="alert alert-warning" role="status">
                        {error}
                      </p>
                    ) : null}
                    {success ? (
                      <p className="alert alert-success" role="status">
                        {success}
                      </p>
                    ) : null}
                    <p className="mono muted">{copy.fieldModeNote}</p>
                  </div>
                )}
              </CardContent>
            </Card>

            <div className="stack-gap-2">
              {surface ? (
                <SurfaceSummary heading={copy.currentSurfaceTitle} surface={surface} copy={copy} />
              ) : null}
              {preview ? (
                <Card variant="detail">
                  <CardHeader>
                    <div className="stack-gap-2">
                      <span className="card-header-title">{copy.previewCardTitle}</span>
                      <span className="mono muted">
                        {preview.can_apply ? copy.previewCardSubtitleReady : copy.previewCardSubtitleBlocked}
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {preview.changes.length === 0 ? (
                      <p className="mono muted">{copy.previewNoChanges}</p>
                    ) : (
                      <div className="data-list">
                        {preview.changes.map((change) => (
                          <div key={`${change.field}:${change.next || "-"}`} className="data-list-row">
                            <span className="data-list-label">{changeLabel(change.field, copy)}</span>
                            <span className="data-list-value mono">
                              {readableValue(change.current, copy.notSetLabel)} → {readableValue(change.next, copy.notSetLabel)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="mt-3">
                      <SurfaceSummary heading={copy.previewSurfaceTitle} surface={preview.preview_surface} copy={copy} />
                    </div>
                  </CardContent>
                </Card>
              ) : null}
            </div>
          </div>
        </details>
      </Card>
    </section>
  );
}
