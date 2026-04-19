import { useEffect, useState } from "react";
import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";

import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../components/ui/Card";
import { Input, Select } from "../components/ui/Input";
import {
  applyRoleConfig,
  fetchRoleConfig,
  mutationExecutionCapability,
  previewRoleConfig,
} from "../lib/api";
import type {
  JsonValue,
  RoleCatalogRecord,
  RoleConfigApplyResponse,
  RoleConfigPreviewResponse,
  RoleConfigSurface,
} from "../lib/types";

type AgentsRoleConfigPanelProps = {
  roleCatalog: RoleCatalogRecord[];
  onApplied: () => Promise<void>;
  locale?: UiLocale;
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

function runnerOptions(locale: UiLocale) {
  return [
    { value: "", label: locale === "zh-CN" ? "继承 / 未解析" : "Inherit / unresolved" },
    { value: "agents", label: "agents" },
    { value: "app_server", label: "app_server" },
    { value: "codex", label: "codex" },
    { value: "claude", label: "claude" },
  ];
}

function panelCopy(locale: UiLocale) {
  if (locale === "zh-CN") {
    return {
      deskTitle: "角色配置桌",
      emptyState: "当前还没有可配置的已注册角色。",
      subtitle: "修改 repo 自有角色默认值，先看派生回读，再只在 fail-closed 检查同意时保存。",
      applyEnabled: (operatorRole: string) => `允许 ${operatorRole} 执行应用`,
      previewOnly: "仅预览",
      editableDefaults: "可编辑默认值",
      role: "角色",
      selectRoleAria: "选择要配置的角色",
      noRolePurpose: "当前还没有发布角色用途说明。",
      loadingRoleConfig: "正在加载角色配置…",
      systemPromptRef: "System prompt ref",
      skillsBundleRef: "Skills bundle ref",
      mcpBundleRef: "MCP bundle ref",
      runtimeRunner: "Runtime runner",
      runtimeProvider: "Runtime provider",
      runtimeModel: "Runtime model",
      previewDefaults: "预览默认值",
      previewing: "预览中...",
      saveDefaults: "保存 repo 默认值",
      saving: "保存中...",
      previewRequiresOperator: "当前可以预览，但保存默认值需要 operator 角色。",
      fieldModes: "字段模式：purpose 仍保留给后续；read model 保持派生；执行权仍由 `task_contract` 掌管。",
      currentDefaults: "当前生效默认值",
      executionAuthority: "Execution authority",
      persistedSource: "持久化来源",
      persistedNote: "这会更新未来编译出来的 contract 所使用的 repo 级角色默认值。正在运行的任务仍遵循当前 task contract。",
      previewReadback: "预览回读",
      previewNoChange: "预览显示与当前生效默认值没有差异。",
      runtimeLane: "Runtime lane",
      toolExecution: "Tool execution",
      unset: "未设置",
      saved: (role: string) => `已为 ${role} 保存 repo 自有默认值。`,
    };
  }
  return {
    deskTitle: "Role configuration desk",
    emptyState: "No registered roles are available for configuration yet.",
    subtitle: "Change repo-owned role defaults, preview the derived readback, then save only when the fail-closed checks agree.",
    applyEnabled: (operatorRole: string) => `Apply enabled for ${operatorRole}`,
    previewOnly: "Preview only",
    editableDefaults: "Editable defaults",
    role: "Role",
    selectRoleAria: "Select role for role configuration",
    noRolePurpose: "No role purpose published yet.",
    loadingRoleConfig: "Loading role configuration…",
    systemPromptRef: "System prompt ref",
    skillsBundleRef: "Skills bundle ref",
    mcpBundleRef: "MCP bundle ref",
    runtimeRunner: "Runtime runner",
    runtimeProvider: "Runtime provider",
    runtimeModel: "Runtime model",
    previewDefaults: "Preview defaults",
    previewing: "Previewing...",
    saveDefaults: "Save repo defaults",
    saving: "Saving...",
    previewRequiresOperator: "Preview is available, but saving defaults requires an operator role.",
    fieldModes: "Field modes: purpose = reserved-for-later; read models stay derived and execution authority stays `task_contract`.",
    currentDefaults: "Current effective defaults",
    executionAuthority: "Execution authority",
    persistedSource: "Persisted source",
    persistedNote: "This updates repo-owned role defaults for future compiled contracts. Running tasks still follow the active task contract.",
    previewReadback: "Preview readback",
    previewNoChange: "Preview shows no change from the current effective defaults.",
    runtimeLane: "Runtime lane",
    toolExecution: "Tool execution",
    unset: "Not set",
    saved: (role: string) => `Saved repo-owned defaults for ${role}.`,
  };
}

function emptyDraft(): RoleConfigDraft {
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

function draftFromSurface(surface: RoleConfigSurface | null): RoleConfigDraft {
  if (!surface) {
    return emptyDraft();
  }
  return {
    system_prompt_ref: surface.editable_now.system_prompt_ref || "",
    skills_bundle_ref: surface.editable_now.skills_bundle_ref || "",
    mcp_bundle_ref: surface.editable_now.mcp_bundle_ref || "",
    runtime_binding: {
      runner: surface.editable_now.runtime_binding.runner || "",
      provider: surface.editable_now.runtime_binding.provider || "",
      model: surface.editable_now.runtime_binding.model || "",
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

function readableValue(value: string | null | undefined, locale: UiLocale): string {
  const normalized = String(value || "").trim();
  return normalized || panelCopy(locale).unset;
}

function changeLabel(field: string, locale: UiLocale): string {
  const mapping: Record<string, string> = {
    system_prompt_ref: panelCopy(locale).systemPromptRef,
    skills_bundle_ref: panelCopy(locale).skillsBundleRef,
    mcp_bundle_ref: panelCopy(locale).mcpBundleRef,
    "runtime_binding.runner": panelCopy(locale).runtimeRunner,
    "runtime_binding.provider": panelCopy(locale).runtimeProvider,
    "runtime_binding.model": panelCopy(locale).runtimeModel,
  };
  return mapping[field] || field;
}

export function AgentsRoleConfigPanel({ roleCatalog, onApplied, locale = "en" }: AgentsRoleConfigPanelProps) {
  const mutationCapability = mutationExecutionCapability();
  const copy = panelCopy(locale);
  const [selectedRole, setSelectedRole] = useState(roleCatalog[0]?.role || "");
  const [surface, setSurface] = useState<RoleConfigSurface | null>(null);
  const [draft, setDraft] = useState<RoleConfigDraft>(emptyDraft());
  const [preview, setPreview] = useState<RoleConfigPreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (!selectedRole) {
      setSurface(null);
      setDraft(emptyDraft());
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

  async function handleApply() {
    if (!selectedRole || !mutationCapability.executable) {
      return;
    }
    setApplying(true);
    setError("");
    setSuccess("");
    try {
      const payload: RoleConfigApplyResponse = await applyRoleConfig(selectedRole, payloadFromDraft(draft));
      setSurface(payload.surface);
      setDraft(draftFromSurface(payload.surface));
      setPreview(null);
      setSuccess(copy.saved(payload.role));
      await onApplied();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setApplying(false);
    }
  }

  if (roleCatalog.length === 0) {
    return (
      <div className="app-section">
        <h2 className="section-title">{copy.deskTitle}</h2>
        <p className="muted">{copy.emptyState}</p>
      </div>
    );
  }

  return (
    <div className="app-section">
      <div className="section-header">
        <div>
          <h2 className="section-title">{copy.deskTitle}</h2>
          <p className="page-subtitle">{copy.subtitle}</p>
        </div>
        <Badge variant={mutationCapability.executable ? "success" : "warning"}>
          {mutationCapability.executable ? copy.applyEnabled(String(mutationCapability.operatorRole || "")) : copy.previewOnly}
        </Badge>
      </div>
      <div className="grid">
        <Card>
          <CardHeader>
            <CardTitle>{copy.editableDefaults}</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="stack-gap-2">
              <label className="stack-gap-2">
                <span className="muted">{copy.role}</span>
                <Select
                  aria-label={copy.selectRoleAria}
                  value={selectedRole}
                  onChange={(event) => {
                    setSelectedRole(event.target.value);
                    setSuccess("");
                    setError("");
                  }}
                >
                  {roleCatalog.map((record) => (
                    <option key={record.role} value={record.role}>
                      {record.role}
                    </option>
                  ))}
                </Select>
              </label>
              <p className="muted">{roleCatalog.find((record) => record.role === selectedRole)?.purpose || copy.noRolePurpose}</p>
              {loading ? <p className="muted">{copy.loadingRoleConfig}</p> : null}
              <label className="stack-gap-2">
                <span className="muted">{copy.systemPromptRef}</span>
                <Input
                  aria-label={copy.systemPromptRef}
                  value={draft.system_prompt_ref}
                  onChange={(event) => setDraft((current) => ({ ...current, system_prompt_ref: event.target.value }))}
                />
              </label>
              <label className="stack-gap-2">
                <span className="muted">{copy.skillsBundleRef}</span>
                <Input
                  aria-label={copy.skillsBundleRef}
                  value={draft.skills_bundle_ref}
                  onChange={(event) => setDraft((current) => ({ ...current, skills_bundle_ref: event.target.value }))}
                />
              </label>
              <label className="stack-gap-2">
                <span className="muted">{copy.mcpBundleRef}</span>
                <Input
                  aria-label={copy.mcpBundleRef}
                  value={draft.mcp_bundle_ref}
                  onChange={(event) => setDraft((current) => ({ ...current, mcp_bundle_ref: event.target.value }))}
                />
              </label>
              <div className="stack-gap-2">
                <label className="stack-gap-2">
                  <span className="muted">{copy.runtimeRunner}</span>
                  <Select
                    aria-label={copy.runtimeRunner}
                    value={draft.runtime_binding.runner}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        runtime_binding: { ...current.runtime_binding, runner: event.target.value },
                      }))
                    }
                  >
                    {runnerOptions(locale).map((item) => (
                      <option key={item.value || "empty"} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </Select>
                </label>
                <label className="stack-gap-2">
                  <span className="muted">{copy.runtimeProvider}</span>
                  <Input
                    aria-label={copy.runtimeProvider}
                    value={draft.runtime_binding.provider}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        runtime_binding: { ...current.runtime_binding, provider: event.target.value },
                      }))
                    }
                  />
                </label>
                <label className="stack-gap-2">
                  <span className="muted">{copy.runtimeModel}</span>
                  <Input
                    aria-label={copy.runtimeModel}
                    value={draft.runtime_binding.model}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        runtime_binding: { ...current.runtime_binding, model: event.target.value },
                      }))
                    }
                  />
                </label>
              </div>
              <div className="toolbar">
                <Button onClick={() => void handlePreview()} disabled={!selectedRole || previewing || loading}>
                  {previewing ? copy.previewing : copy.previewDefaults}
                </Button>
                <Button onClick={() => void handleApply()} disabled={!selectedRole || applying || !mutationCapability.executable}>
                  {applying ? copy.saving : copy.saveDefaults}
                </Button>
              </div>
              {!mutationCapability.executable ? (
                <p className="muted">{copy.previewRequiresOperator}</p>
              ) : null}
              {error ? <p className="alert alert-danger">{error}</p> : null}
              {success ? <p className="alert alert-success">{success}</p> : null}
              <p className="mono muted">{copy.fieldModes}</p>
            </div>
          </CardBody>
        </Card>

        {surface ? (
          <Card>
            <CardHeader>
              <CardTitle>{copy.currentDefaults}</CardTitle>
            </CardHeader>
            <CardBody>
              <div className="data-list">
                <div className="data-list-row"><span className="data-list-label">{copy.systemPromptRef}</span><span className="data-list-value mono">{readableValue(surface.editable_now.system_prompt_ref, locale)}</span></div>
                <div className="data-list-row"><span className="data-list-label">{copy.skillsBundleRef}</span><span className="data-list-value mono">{readableValue(surface.editable_now.skills_bundle_ref, locale)}</span></div>
                <div className="data-list-row"><span className="data-list-label">{copy.mcpBundleRef}</span><span className="data-list-value mono">{readableValue(surface.editable_now.mcp_bundle_ref, locale)}</span></div>
                <div className="data-list-row"><span className="data-list-label">Runtime binding</span><span className="data-list-value mono">{readableValue(surface.editable_now.runtime_binding.runner, locale)} / {readableValue(surface.editable_now.runtime_binding.provider, locale)} / {readableValue(surface.editable_now.runtime_binding.model, locale)}</span></div>
                <div className="data-list-row"><span className="data-list-label">{copy.executionAuthority}</span><span className="data-list-value">{surface.execution_authority}</span></div>
              </div>
              <p className="mono muted">{copy.persistedSource}: {surface.persisted_source}</p>
              <p className="muted">{copy.persistedNote}</p>
            </CardBody>
          </Card>
        ) : null}

        {preview ? (
          <Card>
            <CardHeader>
              <CardTitle>{copy.previewReadback}</CardTitle>
            </CardHeader>
            <CardBody>
              {preview.changes.length === 0 ? (
                <p className="muted">{copy.previewNoChange}</p>
              ) : (
                <div className="data-list">
                  {preview.changes.map((change) => (
                    <div key={`${change.field}:${change.next || "-"}`} className="data-list-row">
                      <span className="data-list-label">{changeLabel(change.field, locale)}</span>
                      <span className="data-list-value mono">{readableValue(change.current, locale)} → {readableValue(change.next, locale)}</span>
                    </div>
                  ))}
                </div>
              )}
              <div className="data-list mt-3">
                <div className="data-list-row"><span className="data-list-label">{copy.runtimeLane}</span><span className="data-list-value mono">{preview.preview_surface.runtime_capability.lane}</span></div>
                <div className="data-list-row"><span className="data-list-label">{copy.toolExecution}</span><span className="data-list-value mono">{preview.preview_surface.runtime_capability.tool_execution}</span></div>
              </div>
            </CardBody>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
