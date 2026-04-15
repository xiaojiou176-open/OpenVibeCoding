"use client";

import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { sanitizeUiError, uiErrorDetail } from "../../lib/uiError";

export default function CommandTowerError({ error, reset }: { error: Error; reset: () => void }) {
  const locale = detectPreferredUiLocale();
  const copy =
    locale === "zh-CN"
      ? {
          fallback: "指挥塔暂时没有加载成功",
          title: "指挥塔暂时没有加载成功",
          description: "实时回读数据暂时不可用。先重新加载；如果还是失败，再检查后端服务、登录状态和运行证据。",
          retry: "重新加载",
        }
      : {
          fallback: "Command Tower failed to load",
          title: "Command Tower failed to load",
          description: "Live read-back is temporarily unavailable. Reload first, then inspect backend health, auth, and run evidence if it still fails.",
          retry: "Retry load",
        };
  const safeMessage = sanitizeUiError(error, copy.fallback);
  console.error(`[command-tower-error-boundary] ${uiErrorDetail(error)}`);

  return (
    <main className="grid" aria-labelledby="command-tower-error-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="command-tower-error-title">{copy.title}</h1>
            <p>{copy.description}</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label="Command Tower error state">
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
