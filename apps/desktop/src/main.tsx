import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";
import { ErrorBoundary } from "./components/layout/ErrorBoundary";
import { initPlatformAttributes } from "./lib/platform";
import { initDesktopRuntimeBridges } from "./lib/runtimeBridge";
import { initDesktopTokens } from "./lib/tokens";

initDesktopTokens();
void initPlatformAttributes();
void initDesktopRuntimeBridges((event) => {
  if (event.level === "error") {
    console.error("[desktop-runtime]", event.code, event.detail);
    return;
  }
  if (event.level === "warning") {
    console.warn("[desktop-runtime]", event.code, event.detail);
    return;
  }
  console.info("[desktop-runtime]", event.code, event.detail);
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
