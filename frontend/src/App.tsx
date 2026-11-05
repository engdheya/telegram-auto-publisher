import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from './layouts/AppLayout';
import { ProtectedRoute } from './components/ProtectedRoute';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { TelegramAccountPage } from './pages/TelegramAccountPage';
import { SourcesPage } from './pages/SourcesPage';
import { TargetsPage } from './pages/TargetsPage';
import { RoutesPage } from './pages/RoutesPage';
import { MessagesPage } from './pages/MessagesPage';
import { QueuePage } from './pages/QueuePage';
import { LogsPage } from './pages/LogsPage';
import { SettingsPage } from './pages/SettingsPage';

const App: React.FC = () => (
  <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route
      element={
        <ProtectedRoute>
          <AppLayout />
        </ProtectedRoute>
      }
    >
      <Route index element={<DashboardPage />} />
      <Route path="/telegram" element={<TelegramAccountPage />} />
      <Route path="/sources" element={<SourcesPage />} />
      <Route path="/targets" element={<TargetsPage />} />
      <Route path="/routes" element={<RoutesPage />} />
      <Route path="/messages" element={<MessagesPage />} />
      <Route path="/queue" element={<QueuePage />} />
      <Route path="/logs" element={<LogsPage />} />
      <Route path="/settings" element={<SettingsPage />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>
);

export default App;
