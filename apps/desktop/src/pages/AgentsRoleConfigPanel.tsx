import { useEffect, useState } from "react";

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

const RUNNER_OPTIONS = [
  { value: "", label: "Inherit / unresolved" },
  { value: "agents", label: "agents" },
  { value: "app_server", label: "app_server" },
  { value: "codex", label: "codex" },
  { value: "claude", label: "claude" },
];

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

function readableValue(value: string | null | undefined): string {
  const normalized = String(value || "").trim();
  return normalized || "Not set";
}

function changeLabel(field: string): string {
  const mapping: Record<string, string> = {
    system_prompt_ref: "System prompt ref",
    skills_bundle_ref: "Skills bundle ref",
    mcp_bundle_ref: "MCP bundle ref",
    "runtime_binding.runner": "Runtime runner",
    "runtime_binding.provider": "Runtime provider",
    "runtime_binding.model": "Runtime model",
  };
  return mapping[field] || field;
}

export function AgentsRoleConfigPanel({ roleCatalog, onApplied }: AgentsRoleConfigPanelProps) {
  const mutationCapability = mutationExecutionCapability();
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
      setSuccess(`Saved repo-owned defaults for ${payload.role}.`);
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
        <h2 className="section-title">Role configuration desk</h2>
        <p className="muted">No registered roles are available for configuration yet.</p>
      </div>
    );
  }

  return (
    <div className="app-section">
      <div className="section-header">
        <div>
          <h2 className="section-title">Role configuration desk</h2>
          <p className="page-subtitle">Change repo-owned role defaults, preview the derived readback, then save only when the fail-closed checks agree.</p>
        </div>
        <Badge variant={mutationCapability.executable ? "success" : "warning"}>
          {mutationCapability.executable ? `Apply enabled for ${mutationCapability.operatorRole}` : "Preview only"}
        </Badge>
      </div>
      <div className="grid">
        <Card>
          <CardHeader>
            <CardTitle>Editable defaults</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="stack-gap-2">
              <label className="stack-gap-2">
                <span className="muted">Role</span>
                <Select
                  aria-label="Select role for role configuration"
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
              <p className="muted">{roleCatalog.find((record) => record.role === selectedRole)?.purpose || "No role purpose published yet."}</p>
              {loading ? <p className="muted">Loading role configuration…</p> : null}
              <label className="stack-gap-2">
                <span className="muted">System prompt ref</span>
                <Input
                  aria-label="System prompt ref"
                  value={draft.system_prompt_ref}
                  onChange={(event) => setDraft((current) => ({ ...current, system_prompt_ref: event.target.value }))}
                />
              </label>
              <label className="stack-gap-2">
                <span className="muted">Skills bundle ref</span>
                <Input
                  aria-label="Skills bundle ref"
                  value={draft.skills_bundle_ref}
                  onChange={(event) => setDraft((current) => ({ ...current, skills_bundle_ref: event.target.value }))}
                />
              </label>
              <label className="stack-gap-2">
                <span className="muted">MCP bundle ref</span>
                <Input
                  aria-label="MCP bundle ref"
                  value={draft.mcp_bundle_ref}
                  onChange={(event) => setDraft((current) => ({ ...current, mcp_bundle_ref: event.target.value }))}
                />
              </label>
              <div className="stack-gap-2">
                <label className="stack-gap-2">
                  <span className="muted">Runtime runner</span>
                  <Select
                    aria-label="Runtime runner"
                    value={draft.runtime_binding.runner}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        runtime_binding: { ...current.runtime_binding, runner: event.target.value },
                      }))
                    }
                  >
                    {RUNNER_OPTIONS.map((item) => (
                      <option key={item.value || "empty"} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </Select>
                </label>
                <label className="stack-gap-2">
                  <span className="muted">Runtime provider</span>
                  <Input
                    aria-label="Runtime provider"
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
                  <span className="muted">Runtime model</span>
                  <Input
                    aria-label="Runtime model"
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
                  {previewing ? "Previewing..." : "Preview defaults"}
                </Button>
                <Button onClick={() => void handleApply()} disabled={!selectedRole || applying || !mutationCapability.executable}>
                  {applying ? "Saving..." : "Save repo defaults"}
                </Button>
              </div>
              {!mutationCapability.executable ? (
                <p className="muted">Preview is available, but saving defaults requires an operator role.</p>
              ) : null}
              {error ? <p className="alert alert-danger">{error}</p> : null}
              {success ? <p className="alert alert-success">{success}</p> : null}
              <p className="mono muted">Field modes: purpose = reserved-for-later; read models stay derived and execution authority stays `task_contract`.</p>
            </div>
          </CardBody>
        </Card>

        {surface ? (
          <Card>
            <CardHeader>
              <CardTitle>Current effective defaults</CardTitle>
            </CardHeader>
            <CardBody>
              <div className="data-list">
                <div className="data-list-row"><span className="data-list-label">System prompt ref</span><span className="data-list-value mono">{readableValue(surface.editable_now.system_prompt_ref)}</span></div>
                <div className="data-list-row"><span className="data-list-label">Skills bundle ref</span><span className="data-list-value mono">{readableValue(surface.editable_now.skills_bundle_ref)}</span></div>
                <div className="data-list-row"><span className="data-list-label">MCP bundle ref</span><span className="data-list-value mono">{readableValue(surface.editable_now.mcp_bundle_ref)}</span></div>
                <div className="data-list-row"><span className="data-list-label">Runtime binding</span><span className="data-list-value mono">{readableValue(surface.editable_now.runtime_binding.runner)} / {readableValue(surface.editable_now.runtime_binding.provider)} / {readableValue(surface.editable_now.runtime_binding.model)}</span></div>
                <div className="data-list-row"><span className="data-list-label">Execution authority</span><span className="data-list-value">{surface.execution_authority}</span></div>
              </div>
              <p className="mono muted">Persisted source: {surface.persisted_source}</p>
              <p className="muted">This updates repo-owned role defaults for future compiled contracts. Running tasks still follow the active task contract.</p>
            </CardBody>
          </Card>
        ) : null}

        {preview ? (
          <Card>
            <CardHeader>
              <CardTitle>Preview readback</CardTitle>
            </CardHeader>
            <CardBody>
              {preview.changes.length === 0 ? (
                <p className="muted">Preview shows no change from the current effective defaults.</p>
              ) : (
                <div className="data-list">
                  {preview.changes.map((change) => (
                    <div key={`${change.field}:${change.next || "-"}`} className="data-list-row">
                      <span className="data-list-label">{changeLabel(change.field)}</span>
                      <span className="data-list-value mono">{readableValue(change.current)} → {readableValue(change.next)}</span>
                    </div>
                  ))}
                </div>
              )}
              <div className="data-list mt-3">
                <div className="data-list-row"><span className="data-list-label">Runtime lane</span><span className="data-list-value mono">{preview.preview_surface.runtime_capability.lane}</span></div>
                <div className="data-list-row"><span className="data-list-label">Tool execution</span><span className="data-list-value mono">{preview.preview_surface.runtime_capability.tool_execution}</span></div>
              </div>
            </CardBody>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
