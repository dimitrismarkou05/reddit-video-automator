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
import { FfmpegMissingModal } from "@/components/ffmpeg/FfmpegMissingModal";
import { useFfmpegStatus } from "@/hooks/useFfmpegStatus";
import { useState } from "react";

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
  const { setAuthStatus, setLoading, authStatus } = useAuthStore();
  const isElectron = !!window.electronAPI;
  const [showFfmpegMissing, setShowFfmpegMissing] = useState(false);
  const [ffmpegSkipped, setFfmpegSkipped] = useState(false);

  const { status: ffmpegStatus, isLoading: ffmpegLoading } = useFfmpegStatus();

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

  // Show FFmpeg missing modal after authentication
  useEffect(() => {
    const isAuthenticated = authStatus?.is_authenticated;

    // Only check FFmpeg if user is authenticated and not loading
    if (
      !ffmpegLoading &&
      isAuthenticated &&
      ffmpegStatus &&
      !ffmpegStatus.can_generate_videos &&
      !ffmpegSkipped
    ) {
      setShowFfmpegMissing(true);
    } else if (!isAuthenticated) {
      // Reset FFmpeg modal state when logged out
      setShowFfmpegMissing(false);
      setFfmpegSkipped(false);
    }
  }, [
    ffmpegLoading,
    ffmpegStatus,
    ffmpegSkipped,
    authStatus?.is_authenticated,
  ]);

  return (
    <div
      className={`${isElectron ? "h-screen" : "min-h-screen"} bg-background-light dark:bg-background-dark text-gray-900 dark:text-gray-100   ${
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

      {showFfmpegMissing && (
        <FfmpegMissingModal
          onClose={() => setShowFfmpegMissing(false)}
          onSkip={() => setFfmpegSkipped(true)}
        />
      )}
    </div>
  );
}

export default App;
