/**
 * App Root Component
 * ===================
 * Sets up routing and authentication guards.
 * Unauthenticated users see the login page.
 * Authenticated users get the full MainLayout with navigation.
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
import { ToastContainer } from "@/components/ui/toast";
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
    <BrowserRouter>
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
          <Route index element={<DashboardPage />} />
          <Route path="storage" element={<StoragePage />} />
          <Route path="apps" element={<AppsPage />} />
          <Route path="network" element={<NetworkPage />} />
          <Route path="protection" element={<ProtectionPage />} />
          <Route path="media" element={<MediaPage />} />
          <Route path="media-manager" element={<MediaManagerPage />} />
          <Route path="keys" element={<KeysPage />} />
          <Route path="system" element={<SystemPage />} />
        </Route>

        {/* Catch-all redirect */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <ToastContainer />
    </BrowserRouter>
  );
}
