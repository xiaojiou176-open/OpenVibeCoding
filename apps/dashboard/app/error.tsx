"use client";

import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { sanitizeUiError, uiErrorDetail } from "../lib/uiError";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  const locale = detectPreferredUiLocale();
  const copy =
    locale === "zh-CN"
      ? {
          fallback: "页面暂时没有加载成功",
          title: "页面暂时没有加载成功",
          description: "这张桌面的数据暂时没有读回来。先重新加载；如果还失败，再检查后端、登录状态和当前权限。",
          retry: "重新加载",
        }
      : {
          fallback: "Page load failed",
          title: "Page load failed",
          description: "This desk could not read back its latest data. Reload first, then inspect backend health, auth, and permissions if it still fails.",
          retry: "Retry load",
        };
  const safeMessage = sanitizeUiError(error, copy.fallback);
  console.error(`[dashboard-error-boundary] ${uiErrorDetail(error)}`);

  return (
    <main className="grid" aria-labelledby="dashboard-error-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="dashboard-error-title">{copy.title}</h1>
            <p>{copy.description}</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label="Error state">
        <Card className="alert alert-danger" role="alert">
          <p className="mono">{safeMessage}</p>
          <div className="toolbar mt-2">
            <Button type="button" variant="default" onClick={reset}>
              {copy.retry}
            </Button>
          </div>
        </Card>
      </section>
    </main>
  );
}
