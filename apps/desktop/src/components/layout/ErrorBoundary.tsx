import React from "react";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import { Button } from "../ui/Button";

type ErrorBoundaryState = {
  hasError: boolean;
  message: string;
};

export class ErrorBoundary extends React.Component<React.PropsWithChildren, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    hasError: false,
    message: ""
  };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    const isZh = detectPreferredUiLocale() === "zh-CN";
    return {
      hasError: true,
      message: error?.message || (isZh ? "桌面壳发生了未预期异常。" : "The desktop shell hit an unexpected error.")
    };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("[desktop-error-boundary]", error.message, errorInfo.componentStack);
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }
    const isZh = detectPreferredUiLocale() === "zh-CN";
    return (
      <main className="desktop-shell" aria-label={isZh ? "错误恢复" : "Error recovery"}>
        <section className="workspace-empty" role="alert">
          <h2>{isZh ? "桌面壳发生异常" : "Something went wrong in the desktop shell"}</h2>
          <p>{this.state.message}</p>
          <Button
            variant="primary"
            onClick={() => {
              window.location.reload();
            }}
          >
            {isZh ? "重新加载" : "Reload"}
          </Button>
        </section>
      </main>
    );
  }
}
