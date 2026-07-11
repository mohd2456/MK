/**
 * ErrorBoundary Component
 * ========================
 * Catches rendering errors in child components and displays
 * a styled fallback UI with a retry button.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Optional fallback component override */
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("[ErrorBoundary] Caught error:", error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex flex-col items-center justify-center min-h-[200px] p-8 rounded-lg border border-mk-border bg-mk-surface">
          <div className="text-center space-y-4">
            <div className="w-12 h-12 mx-auto rounded-full bg-red-500/10 flex items-center justify-center">
              <svg
                className="w-6 h-6 text-red-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
                />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-mk-text-primary">
                Something went wrong
              </h3>
              <p className="text-sm text-mk-text-muted mt-1">
                {this.state.error?.message || "An unexpected error occurred"}
              </p>
            </div>
            <Button onClick={this.handleRetry} variant="secondary" size="sm">
              Try Again
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
