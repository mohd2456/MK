/**
 * App Root Component
 * ===================
 * Sets up routing and authentication guards.
 * Unauthenticated users see the login page.
 * Authenticated users get the full MainLayout with navigation.
 * Wrapped with ErrorBoundary for graceful error recovery.
 */

import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { MainLayout } from "@/components/layout/MainLayout";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { StoragePage } from "@/pages/StoragePage";
import { AppsPage } from "@/pages/AppsPage";
import { NetworkPage } from "@/pages/NetworkPage";
import { ProtectionPage } from "@/pages/ProtectionPage";
import { MediaPage } from "@/pages/MediaPage";
import { MediaManagerPage } from "@/pages/MediaManagerPage";
import { SystemPage } from "@/pages/SystemPage";
import { useAuthStore } from "@/stores/authStore";
import { KeysPage } from "@/pages/KeysPage";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { OfflineIndicator } from "@/components/OfflineIndicator";

/**
 * Route guard: redirects to login if not authenticated.
 */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <OfflineIndicator />
        <Routes>
          {/* Public route */}
          <Route path="/login" element={<LoginPage />} />

          {/* Protected routes with shared layout */}
          <Route
            element={
              <ProtectedRoute>
                <MainLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<ErrorBoundary><DashboardPage /></ErrorBoundary>} />
            <Route path="storage" element={<ErrorBoundary><StoragePage /></ErrorBoundary>} />
            <Route path="apps" element={<ErrorBoundary><AppsPage /></ErrorBoundary>} />
            <Route path="network" element={<ErrorBoundary><NetworkPage /></ErrorBoundary>} />
            <Route path="protection" element={<ErrorBoundary><ProtectionPage /></ErrorBoundary>} />
            <Route path="media" element={<ErrorBoundary><MediaPage /></ErrorBoundary>} />
            <Route path="media-manager" element={<ErrorBoundary><MediaManagerPage /></ErrorBoundary>} />
            <Route path="keys" element={<ErrorBoundary><KeysPage /></ErrorBoundary>} />
            <Route path="system" element={<ErrorBoundary><SystemPage /></ErrorBoundary>} />
          </Route>

          {/* Catch-all redirect */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
