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
  return (
    <aside className={`context-panel ${pinned ? "is-pinned" : ""}`.trim()} aria-label="Context drawer">
      <h2>Context Drawer</h2>
      <p>{pinned ? "Pinned mode is on" : "Adaptive mode is on"}</p>
      <div className="quick-actions">
        <Button
          variant={soundEnabled ? "primary" : "secondary"}
          onClick={() => setSoundEnabled((value) => !value)}
        >
          {soundEnabled ? "Sound alerts: on" : "Sound alerts: off"}
        </Button>
      </div>
      <section className="metrics-grid" aria-label="Overview metrics">
        {overviewMetrics.map((metric) => (
          <article key={metric.label} className="metric-card">
            <p>{metric.label}</p>
            <strong>{metric.value}</strong>
            <small>{metric.detail}</small>
          </article>
        ))}
      </section>
      <section className="ui-card" aria-label="Alert list">
        <h3 className="ui-card-title">System Alerts</h3>
        <ul className="list-grid">
          {alerts.length === 0 ? (
            <li className="list-row">
              <strong>No alerts</strong>
              <span>Policy gates are stable</span>
              <span className="status-badge status-pass">Pass</span>
            </li>
          ) : (
            alerts.slice(0, 6).map((alert) => {
              const tone = alertSeverityToBadge(alert.severity);
              return (
                <li key={`${alert.code || "alert"}-${alert.message || "message"}`} className="list-row">
                  <strong>{alert.code || "ALERT"}</strong>
                  <span>{alert.message || "Details pending"}</span>
                  <span className={`status-badge status-${tone.tone}`}>{tone.label}</span>
                </li>
              );
            })
          )}
        </ul>
      </section>
      <section className="ui-card" aria-label="Hotkey list">
        <h3 className="ui-card-title">Hotkeys</h3>
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
