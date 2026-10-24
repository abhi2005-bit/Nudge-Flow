import React, { Suspense, lazy } from 'react';
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
} from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import AppShell from './components/layout/AppShell';
import './index.css';

// ── Lazy pages ─────────────────────────────────────────────────────────────────
const LoginPage        = lazy(() => import('./pages/auth/LoginPage'));
const RegisterPage     = lazy(() => import('./pages/auth/RegisterPage'));
const DashboardPage    = lazy(() => import('./pages/DashboardPage'));
const ContactsPage     = lazy(() => import('./pages/contacts/ContactsPage'));
const ContactDetailPage= lazy(() => import('./pages/contacts/ContactDetailPage'));
const FollowUpsPage    = lazy(() => import('./pages/followups/FollowUpsPage'));
const FollowUpDetailPage = lazy(() => import('./pages/followups/FollowUpDetailPage'));
const AgentConsolePage = lazy(() => import('./pages/agent/AgentConsolePage'));
const AgentRunPage     = lazy(() => import('./pages/agent/AgentRunPage'));
const SettingsPage     = lazy(() => import('./pages/settings/SettingsPage'));
const NotFoundPage     = lazy(() => import('./pages/NotFoundPage'));

// ── Query client ───────────────────────────────────────────────────────────────
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

// ── Route guards ───────────────────────────────────────────────────────────────
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RequireGuest({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (isAuthenticated) return <Navigate to="/" replace />;
  return <>{children}</>;
}

// ── Page loader ────────────────────────────────────────────────────────────────
function PageLoader() {
  return (
    <div className="loading-overlay">
      <div className="spinner spinner-lg" />
      <span>Loading…</span>
    </div>
  );
}

// ── App ────────────────────────────────────────────────────────────────────────
export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              {/* Public routes */}
              <Route
                path="/login"
                element={
                  <RequireGuest>
                    <LoginPage />
                  </RequireGuest>
                }
              />
              <Route
                path="/register"
                element={
                  <RequireGuest>
                    <RegisterPage />
                  </RequireGuest>
                }
              />

              {/* Protected routes inside the app shell */}
              <Route
                path="/"
                element={
                  <RequireAuth>
                    <AppShell />
                  </RequireAuth>
                }
              >
                <Route index element={<DashboardPage />} />
                <Route path="contacts" element={<ContactsPage />} />
                <Route path="contacts/:id" element={<ContactDetailPage />} />
                <Route path="follow-ups" element={<FollowUpsPage />} />
                <Route path="follow-ups/:id" element={<FollowUpDetailPage />} />
                <Route path="agent" element={<AgentConsolePage />} />
                <Route path="agent/runs/:runId" element={<AgentRunPage />} />
                <Route path="settings" element={<SettingsPage />} />
              </Route>

              {/* Catch-all */}
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
