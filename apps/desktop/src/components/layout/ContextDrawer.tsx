import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import { Button } from "../ui/Button";
import { alertSeverityToBadge } from "../../lib/status";
import type { DesktopAlert } from "../../lib/api";
import type { OverviewMetric } from "../../hooks/useDesktopData";
import { desktopHotkeys } from "../../hotkeys";

type ContextDrawerProps = {
  visible: boolean;
  pinned: boolean;
  soundEnabled: boolean;
  setSoundEnabled: (updater: (value: boolean) => boolean) => void;
  overviewMetrics: OverviewMetric[];
  alerts: DesktopAlert[];
};

export function ContextDrawer({
  visible,
  pinned,
  soundEnabled,
  setSoundEnabled,
  overviewMetrics,
  alerts
}: ContextDrawerProps) {
  if (!visible) {
    return null;
  }
  const isZh = detectPreferredUiLocale() === "zh-CN";
  return (
    <aside className={`context-panel ${pinned ? "is-pinned" : ""}`.trim()} aria-label={isZh ? "上下文抽屉" : "Context drawer"}>
      <h2>{isZh ? "上下文抽屉" : "Context Drawer"}</h2>
      <p>{pinned ? (isZh ? "当前为固定模式" : "Pinned mode is on") : (isZh ? "当前为自适应模式" : "Adaptive mode is on")}</p>
      <div className="quick-actions">
        <Button
          variant={soundEnabled ? "primary" : "secondary"}
          onClick={() => setSoundEnabled((value) => !value)}
        >
          {soundEnabled ? (isZh ? "声音提醒：开" : "Sound alerts: on") : (isZh ? "声音提醒：关" : "Sound alerts: off")}
        </Button>
      </div>
      <section className="metrics-grid" aria-label={isZh ? "总览指标" : "Overview metrics"}>
        {overviewMetrics.map((metric) => (
          <article key={metric.label} className="metric-card">
            <p>{metric.label}</p>
            <strong>{metric.value}</strong>
            <small>{metric.detail}</small>
          </article>
        ))}
      </section>
      <section className="ui-card" aria-label={isZh ? "告警列表" : "Alert list"}>
        <h3 className="ui-card-title">{isZh ? "系统告警" : "System Alerts"}</h3>
        <ul className="list-grid">
          {alerts.length === 0 ? (
            <li className="list-row">
              <strong>{isZh ? "当前无告警" : "No alerts"}</strong>
              <span>{isZh ? "策略门禁稳定" : "Policy gates are stable"}</span>
              <span className="status-badge status-pass">{isZh ? "通过" : "Pass"}</span>
            </li>
          ) : (
            alerts.slice(0, 6).map((alert) => {
              const tone = alertSeverityToBadge(alert.severity);
              return (
                <li key={`${alert.code || "alert"}-${alert.message || "message"}`} className="list-row">
                  <strong>{alert.code || (isZh ? "告警" : "ALERT")}</strong>
                  <span>{alert.message || (isZh ? "细节待补" : "Details pending")}</span>
                  <span className={`status-badge status-${tone.tone}`}>{tone.label}</span>
                </li>
              );
            })
          )}
        </ul>
      </section>
      <section className="ui-card" aria-label={isZh ? "快捷键列表" : "Hotkey list"}>
        <h3 className="ui-card-title">{isZh ? "快捷键" : "Hotkeys"}</h3>
        <ul className="hotkey-list">
          {desktopHotkeys.map((item) => (
            <li key={item.combo}>
              <kbd>{item.combo}</kbd>
              <span>{item.description}</span>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}
