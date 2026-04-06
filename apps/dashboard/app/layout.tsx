import type { CSSProperties, ReactNode } from "react";
import DashboardShellChrome from "../components/DashboardShellChrome";
import WebVitalsBridge from "../components/WebVitalsBridge";
import "./globals.css";

export const metadata = {
  title: "CortexPilot | AI Work Command Tower for Codex, Claude Code, and MCP",
  description:
    "Operate Codex and Claude Code workflows through one AI Work Command Tower with Workflow Cases, Model Context Protocol (MCP)-readable proof and replay, public first-run cases, and one governed operator path.",
};

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
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
        <DashboardShellChrome>{children}</DashboardShellChrome>
      </body>
    </html>
  );
}
