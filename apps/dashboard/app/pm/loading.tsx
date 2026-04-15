import { cookies } from "next/headers";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@openvibecoding/frontend-shared/uiLocale";
import { Card } from "../../components/ui/card";

export default async function PmPageLoading() {
  const cookieStore = await cookies();
  const locale = normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  const copy =
    locale === "zh-CN"
      ? {
          title: "正在加载 PM 工作台",
          subtitle: "会话、聊天上下文和首轮控制信息正在同步，请稍候。",
          ariaLabel: "PM 页面加载状态",
        }
      : {
          title: "Loading the PM workspace",
          subtitle: "Syncing sessions and chat context. Please wait.",
          ariaLabel: "PM page loading state",
        };
  return (
    <main className="grid" aria-labelledby="pm-loading-title" aria-busy="true">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="pm-loading-title">{copy.title}</h1>
            <p>{copy.subtitle}</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label={copy.ariaLabel}>
        <Card className="skeleton-stack-lg">
          <div className="skeleton skeleton-heading skeleton-w-45" />
          <div className="skeleton-stack-md">
            <div className="skeleton skeleton-input-narrow" />
            <div className="skeleton skeleton-input-wide" />
            <div className="skeleton skeleton-block" />
          </div>
          <div className="skeleton skeleton-btn" />
        </Card>
      </section>
    </main>
  );
}
