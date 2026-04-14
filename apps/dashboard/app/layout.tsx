import type { CSSProperties, ReactNode } from "react";
import DashboardShellChrome from "../components/DashboardShellChrome";
import WebVitalsBridge from "../components/WebVitalsBridge";
import "./globals.css";

export const metadata = {
  title: "OpenVibeCoding | The open command tower for AI engineering",
  description:
    "Stop babysitting AI coding work. AI coding does not lack models. It lacks a command tower. OpenVibeCoding is the public shell for the OpenVibeCoding runtime across Codex, Claude Code, Workflow Cases, and replayable proof.",
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
