"use client";

import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { sanitizeUiError, uiErrorDetail } from "../../lib/uiError";

export default function PmPageError({ error, reset }: { error: Error; reset: () => void }) {
  const locale = detectPreferredUiLocale();
  const copy =
    locale === "zh-CN"
      ? {
          fallback: "PM 工作台暂时没有加载成功",
          title: "PM 工作台暂时没有加载成功",
          description: "会话或消息数据暂时没有读回来。先重新加载；如果还是失败，再检查后端服务和当前登录状态。",
          retry: "重新加载",
        }
      : {
          fallback: "Failed to load the PM workspace",
          title: "Failed to load the PM workspace",
          description: "Session or message data is temporarily unavailable. Reload first, then inspect backend health and auth if it still fails.",
          retry: "Retry loading",
        };
  const safeMessage = sanitizeUiError(error, copy.fallback);
  console.error(`[pm-page-error-boundary] ${uiErrorDetail(error)}`);

  return (
    <main className="grid" aria-labelledby="pm-error-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="pm-error-title">{copy.title}</h1>
            <p>{copy.description}</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label="PM page error state">
        <Card className="alert alert-danger" role="alert">
          <p className="mono">{safeMessage}</p>
          <div className="toolbar mt-2">
            <Button variant="default" onClick={reset}>
              {copy.retry}
            </Button>
          </div>
        </Card>
      </section>
    </main>
  );
}
