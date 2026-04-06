"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

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

const RUNNER_OPTIONS = [
  { value: "", label: "Inherit / unresolved" },
  { value: "agents", label: "agents" },
  { value: "app_server", label: "app_server" },
  { value: "codex", label: "codex" },
  { value: "claude", label: "claude" },
];

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

function readableValue(value: string | null | undefined): string {
  const normalized = String(value || "").trim();
  return normalized || "Not set";
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

function RuntimeCapabilityBlock({ surface }: { surface: RoleConfigSurface }) {
  const capability = runtimeCapabilitySummary(surface);
  return (
    <div className="data-list">
      <div className="data-list-row">
        <span className="data-list-label">Capability lane</span>
        <span className="data-list-value mono">{capability.lane}</span>
      </div>
      <div className="data-list-row">
        <span className="data-list-label">Compat API mode</span>
        <span className="data-list-value mono">{capability.compatApiMode}</span>
      </div>
      <div className="data-list-row">
        <span className="data-list-label">Provider status</span>
        <span className="data-list-value mono">{capability.providerStatus}</span>
      </div>
      <div className="data-list-row">
        <span className="data-list-label">Tool execution</span>
        <span className="data-list-value mono">{capability.toolExecution}</span>
      </div>
      <div className="data-list-row">
        <span className="data-list-label">Notes</span>
        <span className="data-list-value">
          <span className="stack-gap-2">
            {capability.notes.map((note) => (
              <span key={note} className="muted">{note}</span>
            ))}
          </span>
        </span>
      </div>
    </div>
  );
}

function SurfaceSummary({
  heading,
  surface,
}: {
  heading: string;
  surface: RoleConfigSurface;
}) {
  const editableNow = editableSurfaceValues(surface);
  return (
    <Card variant="detail">
      <CardHeader>
        <div className="stack-gap-2">
          <span className="card-header-title">{heading}</span>
          <span className="mono muted">
            {surface.authority} / {surface.overlay_state} / {surface.validation}
          </span>
        </div>
      </CardHeader>
      <CardContent>
        <div className="data-list">
          <div className="data-list-row">
            <span className="data-list-label">System prompt ref</span>
            <span className="data-list-value mono">{readableValue(editableNow.system_prompt_ref)}</span>
          </div>
          <div className="data-list-row">
            <span className="data-list-label">Skills bundle ref</span>
            <span className="data-list-value mono">{readableValue(editableNow.skills_bundle_ref)}</span>
          </div>
          <div className="data-list-row">
            <span className="data-list-label">MCP bundle ref</span>
            <span className="data-list-value mono">{readableValue(editableNow.mcp_bundle_ref)}</span>
          </div>
          <div className="data-list-row">
            <span className="data-list-label">Runtime binding</span>
            <span className="data-list-value mono">
              {readableValue(editableNow.runtime_binding.runner)} / {readableValue(editableNow.runtime_binding.provider)} / {readableValue(editableNow.runtime_binding.model)}
            </span>
          </div>
          <div className="data-list-row">
            <span className="data-list-label">Execution authority</span>
            <span className="data-list-value">
              <Badge variant="running">{surface.execution_authority}</Badge>
            </span>
          </div>
        </div>
        <div className="stack-gap-2 mt-3">
          <p className="mono muted">Persisted source: {surface.persisted_source}</p>
          <p className="muted">This updates repo-owned role defaults for future compiled contracts. Running tasks still follow the active task contract.</p>
        </div>
        <div className="mt-3">
          <RuntimeCapabilityBlock surface={surface} />
        </div>
      </CardContent>
    </Card>
  );
}

export function RoleConfigControlPlane({ roleCatalog }: RoleConfigControlPlaneProps) {
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
    () => roleCatalog.map((record) => ({ role: record.role, purpose: record.purpose || "No role purpose published yet." })),
    [roleCatalog],
  );

  const applyDisabledReason = mutationCapability.executable
    ? ""
    : "Preview is available, but saving defaults requires an operator role.";

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
        setSuccess(`Saved repo-owned defaults for ${payload.role}.`);
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
            <h2 id="role-config-control-plane-title" className="section-title">Role configuration desk</h2>
            <p className="mono muted">No roles are registered yet, so the control plane cannot hydrate a config form.</p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="app-section" aria-labelledby="role-config-control-plane-title">
      <div className="section-header">
        <div>
          <h2 id="role-config-control-plane-title" className="section-title">Role configuration desk</h2>
          <p className="page-subtitle">Change repo-owned role defaults, preview the derived readback, then save only when the fail-closed checks agree.</p>
        </div>
        <Badge variant={mutationCapability.executable ? "success" : "warning"}>
          {mutationCapability.executable ? `Apply enabled for ${mutationCapability.operatorRole}` : "Preview only"}
        </Badge>
      </div>

      <div className="grid-2">
        <Card variant="detail">
          <CardHeader>
            <div className="stack-gap-2">
              <span className="card-header-title">Editable defaults</span>
              <span className="mono muted">Scope: `system_prompt_ref`, `skills_bundle_ref`, `mcp_bundle_ref`, `runtime_binding`</span>
            </div>
          </CardHeader>
          <CardContent>
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
                  {roleOptions.map((item) => (
                    <option key={item.role} value={item.role}>
                      {item.role}
                    </option>
                  ))}
                </Select>
              </label>
              <p className="muted">
                {roleOptions.find((item) => item.role === selectedRole)?.purpose || "No role purpose published yet."}
              </p>
            </div>

            {loading ? (
              <p className="mono muted">Loading role configuration…</p>
            ) : (
              <div className="stack-gap-2 mt-3">
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
                <div className="grid-2">
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
                </div>
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
                <div className="toolbar toolbar--mt">
                  <Button onClick={() => void handlePreview()} disabled={!selectedRole || previewing || loading}>
                    {previewing ? "Previewing…" : "Preview defaults"}
                  </Button>
                  <Button onClick={handleApply} disabled={!selectedRole || applying || !mutationCapability.executable}>
                    {applying ? "Saving…" : "Save repo defaults"}
                  </Button>
                </div>
                {applyDisabledReason ? (
                  <p className="mono muted">{applyDisabledReason}</p>
                ) : null}
                {error ? <p className="alert alert-warning" role="status">{error}</p> : null}
                {success ? <p className="alert alert-success" role="status">{success}</p> : null}
                <p className="mono muted">
                  Field modes: purpose = reserved-for-later; read models stay derived and execution authority stays `task_contract`.
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="stack-gap-2">
          {surface ? <SurfaceSummary heading="Current effective defaults" surface={surface} /> : null}
          {preview ? (
            <Card variant="detail">
              <CardHeader>
                <div className="stack-gap-2">
                  <span className="card-header-title">Preview readback</span>
                  <span className="mono muted">
                    {preview.can_apply ? "Validated preview (fail-closed)" : "Preview blocked"}
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                {preview.changes.length === 0 ? (
                  <p className="mono muted">Preview shows no change from the current effective defaults.</p>
                ) : (
                  <div className="data-list">
                    {preview.changes.map((change) => (
                      <div key={`${change.field}:${change.next || "-"}`} className="data-list-row">
                        <span className="data-list-label">{changeLabel(change.field)}</span>
                        <span className="data-list-value mono">
                          {readableValue(change.current)} → {readableValue(change.next)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                <div className="mt-3">
                  <SurfaceSummary heading="Previewed effective defaults" surface={preview.preview_surface} />
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </section>
  );
}
