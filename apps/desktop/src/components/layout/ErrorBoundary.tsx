import React from "react";
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
    return {
      hasError: true,
      message: error?.message || "The desktop shell hit an unexpected error."
    };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("[desktop-error-boundary]", error.message, errorInfo.componentStack);
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }
    return (
      <main className="desktop-shell" aria-label="Error recovery">
        <section className="workspace-empty" role="alert">
          <h2>Something went wrong in the desktop shell</h2>
          <p>{this.state.message}</p>
          <Button
            variant="primary"
            onClick={() => {
              window.location.reload();
            }}
          >
            Reload
          </Button>
        </section>
      </main>
    );
  }
}
