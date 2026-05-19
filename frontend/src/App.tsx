import { useEffect } from "react";
import { Routes, Route, Navigate, Outlet, useParams } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { useThemeStore, useAuthStore } from "@/store";
import { Layout } from "@/components/Layout";
import { LoginPage } from "@/pages/LoginPage";
import { StoriesPage } from "@/pages/StoriesPage";
import { VideosPage } from "@/pages/VideosPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { AutomationPage } from "@/pages/AutomationPage";
import { StoryDetailPage } from "@/pages/StoryDetailPage";
import { youtubeApi } from "@/services/api";
import { PublicSettingsPage } from "@/pages/PublicSettingsPage";
import { TitleBar } from "@/components/TitleBar";

function ProtectedRoute() {
  const { authStatus, isLoading } = useAuthStore();
  const electron = !!window.electronAPI;

  if (isLoading) {
    return (
      <div
        className={`${electron ? "h-full" : "min-h-screen"} flex items-center justify-center bg-background-light dark:bg-background-dark`}
      >
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (!authStatus?.is_authenticated) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

function PublicOnlyRoute() {
  const { authStatus, isLoading } = useAuthStore();
  const electron = !!window.electronAPI;

  if (isLoading) {
    return (
      <div
        className={`${electron ? "h-full" : "min-h-screen"} flex items-center justify-center bg-background-light dark:bg-background-dark`}
      >
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (authStatus?.is_authenticated) {
    return <Navigate to="/stories" replace />;
  }

  return <Outlet />;
}

function StoryDetailWrapper() {
  const { id } = useParams();
  return <StoryDetailPage key={id} />;
}

function App() {
  const { isDark } = useThemeStore();
  const { setAuthStatus, setLoading } = useAuthStore();
  const isElectron = !!window.electronAPI;

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
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

  return (
    <div
      className={`${isElectron ? "h-screen" : "min-h-screen"} bg-background-light dark:bg-background-dark text-gray-900 dark:text-gray-100 transition-colors duration-200 ${
        isElectron ? "flex flex-col overflow-hidden" : ""
      }`}
    >
      {isElectron && <TitleBar />}
      <Toaster
        position="bottom-right"
        toastOptions={{
          className: "dark:bg-surface-dark dark:text-white",
          duration: 4000,
        }}
      />
      <div className={isElectron ? "flex-1 overflow-hidden" : ""}>
        <Routes>
          <Route element={<PublicOnlyRoute />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/setup" element={<PublicSettingsPage />} />
          </Route>
          <Route element={<ProtectedRoute />}>
            <Route element={<Layout />}>
              <Route path="/stories" element={<StoriesPage />} />
              <Route path="/stories/:id" element={<StoryDetailWrapper />} />
              <Route path="/videos" element={<VideosPage />} />
              <Route path="/automation" element={<AutomationPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/" element={<Navigate to="/stories" replace />} />
            </Route>
          </Route>
        </Routes>
      </div>
    </div>
  );
}

export default App;
