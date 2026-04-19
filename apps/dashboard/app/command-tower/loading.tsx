import { cookies } from "next/headers";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@openvibecoding/frontend-shared/uiLocale";

export default async function CommandTowerLoading() {
  const cookieStore = await cookies();
  const locale = normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  const copy =
    locale === "zh-CN"
      ? {
          title: "正在加载指挥塔",
          subtitle: "请稍候，系统正在聚合会话总览、告警和实时状态。",
          ariaLabel: "指挥塔加载状态",
        }
      : {
          title: "Loading Command Tower",
          subtitle: "Gathering session overview, alerts, and live status. Please wait.",
          ariaLabel: "Command Tower loading state",
        };

  return (
    <main className="grid" aria-labelledby="command-tower-loading-title" aria-busy="true">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="command-tower-loading-title">{copy.title}</h1>
            <p>{copy.subtitle}</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label={copy.ariaLabel}>
        <div className="stats-grid">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="metric-card skeleton-stack">
              <div className="skeleton skeleton-text skeleton-w-50" />
              <div className="skeleton skeleton-metric skeleton-w-40" />
            </div>
          ))}
        </div>
        <div className="grid-2 skeleton-gap-top">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton skeleton-card skeleton-card-tall" />
          ))}
        </div>
      </section>
    </main>
  );
}
