import type { CSSProperties, ReactNode } from "react";
import { cookies } from "next/headers";
import type { Metadata } from "next";
import DashboardShellChrome from "../components/DashboardShellChrome";
import WebVitalsBridge from "../components/WebVitalsBridge";
import "./globals.css";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY, type UiLocale } from "@openvibecoding/frontend-shared/uiLocale";

export function buildDashboardLayoutMetadata(locale: UiLocale): Metadata {
  if (locale === "zh-CN") {
    return {
      title: "OpenVibeCoding | 面向 AI 工程的开放指挥塔",
      description:
        "别再盯着 AI 编码一步一步催了。AI 编码不缺模型，缺的是指挥塔。OpenVibeCoding 是面向 Codex、Claude Code、工作流案例以及可回放证明路径的开放指挥塔。",
    };
  }

  return {
    title: "OpenVibeCoding | The open command tower for AI engineering",
    description:
      "Stop babysitting AI coding work. AI coding does not lack models. It lacks a command tower. OpenVibeCoding is the open command tower for AI engineering across Codex, Claude Code, Workflow Cases, and replayable proof.",
  };
}

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function generateMetadata(): Promise<Metadata> {
  const cookieStore = await cookies();
  const locale = normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  return buildDashboardLayoutMetadata(locale);
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const cookieStore = await cookies();
  const initialLocale = normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);

  return (
    <html lang={initialLocale}>
      <body
        className="app-body"
        style={
          {
            "--font-manrope": '"Manrope"',
            "--font-space-grotesk": '"Space Grotesk"',
            "--font-jetbrains-mono": '"JetBrains Mono"',
          } as CSSProperties
        }
      >
        <WebVitalsBridge />
        <DashboardShellChrome initialLocale={initialLocale}>{children}</DashboardShellChrome>
      </body>
    </html>
  );
}
