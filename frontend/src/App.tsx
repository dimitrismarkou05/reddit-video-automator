import React, { useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { useThemeStore, useAuthStore } from '@/store';
import { Layout } from '@/components/Layout';
import { LoginPage } from '@/pages/LoginPage';
import { StoriesPage } from '@/pages/StoriesPage';
import { VideosPage } from '@/pages/VideosPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { AutomationPage } from '@/pages/AutomationPage';
import { youtubeApi } from '@/services/api';

function App() {
  const { isDark } = useThemeStore();
  const { authStatus, setAuthStatus, setLoading } = useAuthStore();

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const { data } = await youtubeApi.authStatus();
        setAuthStatus(data);
      } catch {
        setAuthStatus(null);
      } finally {
        setLoading(false);
      }
    };
    checkAuth();
  }, [setAuthStatus, setLoading]);

  if (authStatus === null && useAuthStore.getState().isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background-light dark:bg-background-dark">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background-light dark:bg-background-dark text-gray-900 dark:text-gray-100 transition-colors duration-200">
      <Toaster
        position="top-right"
        toastOptions={{
          className: 'dark:bg-surface-dark dark:text-white',
          duration: 4000,
        }}
      />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<Layout />}>
          <Route path="/stories" element={<StoriesPage />} />
          <Route path="/videos" element={<VideosPage />} />
          <Route path="/automation" element={<AutomationPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/" element={<Navigate to="/stories" replace />} />
        </Route>
      </Routes>
    </div>
  );
}

export default App;
