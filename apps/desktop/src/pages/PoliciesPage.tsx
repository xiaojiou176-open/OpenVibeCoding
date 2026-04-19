import { useCallback, useEffect, useState } from "react";
import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import type { JsonValue } from "../lib/types";
import { fetchPolicies } from "../lib/api";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../components/ui/Card";

const POLICY_SECTIONS = [
  "control_plane_runtime_policy",
  "agent_registry",
  "command_allowlist",
  "forbidden_actions",
  "tool_registry",
] as const;
const SECTION_LABELS: Record<string, string> = {
  control_plane_runtime_policy: "Control-plane runtime policy",
  agent_registry: "Agent registry",
  command_allowlist: "Command allowlist",
  forbidden_actions: "Forbidden actions",
  tool_registry: "Tool registry",
};

export function PoliciesPage({ locale = detectPreferredUiLocale() as UiLocale }: { locale?: UiLocale } = {}) {
  const copy = locale === "zh-CN"
    ? {
        title: "策略",
        subtitle: "从同一张策略桌审计控制平面运行规则、角色注册表、命令白名单、工具权限和禁用动作。",
        refresh: "刷新",
        refreshing: "刷新中...",
        noData: "暂无数据",
        sections: {
          control_plane_runtime_policy: "控制平面运行策略",
          agent_registry: "智能体注册表",
          command_allowlist: "命令白名单",
          forbidden_actions: "禁用动作",
          tool_registry: "工具注册表",
        },
      }
    : {
        title: "Policies",
        subtitle: "Audit control-plane runtime rules, agent registry, command allowlist, tool permissions, and forbidden actions from one policy desk.",
        refresh: "Refresh",
        refreshing: "Refreshing...",
        noData: "No data",
        sections: SECTION_LABELS,
      };
  const [policies, setPolicies] = useState<Record<string, JsonValue>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setPolicies(await fetchPolicies()); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="content">
      <div className="section-header"><div><h1 className="page-title">{copy.title}</h1><p className="page-subtitle">{copy.subtitle}</p></div><Button onClick={load} disabled={loading}>{loading ? copy.refreshing : copy.refresh}</Button></div>
      {error && <div className="alert alert-danger" role="alert" aria-live="assertive">{error}</div>}
      {loading ? <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div> : (
        <div className="grid-2">
          {POLICY_SECTIONS.map((key) => {
            const data = policies[key];
            return (
              <Card key={key}>
                <CardHeader>
                  <CardTitle>{copy.sections[key] || key}</CardTitle>
                </CardHeader>
                <CardBody>
                  {data ? <pre className="pre-scroll-320">{typeof data === "string" ? data : JSON.stringify(data, null, 2)}</pre> : <p className="muted">{copy.noData}</p>}
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
