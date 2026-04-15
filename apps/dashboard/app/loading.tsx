import { cookies } from "next/headers";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@openvibecoding/frontend-shared/uiLocale";
import { Card } from "../components/ui/card";

export default async function Loading() {
  const cookieStore = await cookies();
  const locale = normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  const copy =
    locale === "zh-CN"
      ? {
          title: "正在加载控制台数据",
          subtitle: "请稍候，系统正在聚合运行、会话和治理信号。",
          ariaLabel: "加载状态",
        }
      : {
          title: "Loading dashboard data",
          subtitle: "Please wait while the control plane aggregates runs, sessions, and governance signals.",
          ariaLabel: "Loading state",
        };
  return (
    <main className="grid" aria-labelledby="dashboard-loading-title" aria-busy="true">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="dashboard-loading-title">{copy.title}</h1>
            <p>{copy.subtitle}</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label={copy.ariaLabel}>
        <div className="stats-grid">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="metric-card skeleton-stack">
              <div className="skeleton skeleton-text skeleton-w-40" />
              <div className="skeleton skeleton-metric" />
            </div>
          ))}
        </div>
        <Card variant="table" className="skeleton-gap-top">
          <div className="skeleton-stack-md">
            <div className="skeleton skeleton-heading" />
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="skeleton skeleton-row" />
            ))}
          </div>
        </Card>
      </section>
    </main>
  );
}
