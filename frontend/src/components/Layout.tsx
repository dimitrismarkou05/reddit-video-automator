import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  BookOpen,
  Video,
  Settings,
  Bot,
  Sun,
  Moon,
  LogOut,
  User,
} from "lucide-react";
import { useThemeStore, useAuthStore, useNotificationStore } from "@/store";
import { NotificationDropdown } from "@/components/NotificationDropdown";
import { youtubeApi } from "@/services/api";
import { useEffect } from "react";

const navItems = [
  { path: "/stories", label: "Stories", icon: BookOpen },
  { path: "/videos", label: "Videos", icon: Video },
  { path: "/automation", label: "Automation", icon: Bot },
  { path: "/settings", label: "Settings", icon: Settings },
];

export function Layout() {
  const { isDark, toggle } = useThemeStore();
  const { authStatus, logout } = useAuthStore();
  const {} = useNotificationStore();
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const main = document.querySelector("main");
    if (main) main.scrollTop = 0;
  }, [location.pathname]);

  const handleLogout = async () => {
    try {
      await youtubeApi.logout();
    } catch (e) {
      console.error("Logout error:", e);
    }
    logout();
    navigate("/login");
  };

  return (
    <div className="flex h-full overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 bg-surface-light dark:bg-surface-dark border-r border-border-light dark:border-border-dark flex flex-col">
        {/* Logo */}
        <div className="p-4 border-b border-border-light dark:border-border-dark">
          <button
            onClick={() => navigate("/stories")}
            className="cursor-pointer flex items-center gap-3"
          >
            <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center">
              <Video className="w-5 h-5 text-white" />
            </div>
            <div className="flex items-start flex-col">
              <h1 className="font-bold text-lg leading-tight">Reddit Video</h1>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Automator
              </p>
            </div>
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-3 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                className={`cursor-pointer w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-primary/10 text-primary dark:bg-primary/20"
                    : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
                }`}
              >
                <Icon className="w-5 h-5" />
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* Bottom section */}
        <div className="p-3 border-t border-border-light dark:border-border-dark space-y-2">
          <button
            onClick={toggle}
            className="cursor-pointer w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            {isDark ? (
              <Sun className="w-5 h-5" />
            ) : (
              <Moon className="w-5 h-5" />
            )}
            {isDark ? "Light Mode" : "Dark Mode"}
          </button>

          {authStatus?.is_authenticated && (
            <div className="flex items-center gap-3 px-3 py-2">
              {authStatus.user_info?.picture ? (
                <img
                  src={authStatus.user_info.picture}
                  alt=""
                  className="w-8 h-8 rounded-full"
                />
              ) : (
                <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center">
                  <User className="w-4 h-4 text-primary" />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">
                  {authStatus.user_info?.name || "Connected"}
                </p>
                <p className="text-xs text-gray-500 truncate">
                  {authStatus.user_info?.email || "YouTube Account"}
                </p>
              </div>
              <button
                onClick={handleLogout}
                className="cursor-pointer p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500"
                title="Logout"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-14 bg-surface-light dark:bg-surface-dark border-b border-border-light dark:border-border-dark flex items-center justify-between px-6">
          <h2 className="text-lg font-semibold">
            {navItems.find((n) => n.path === location.pathname)?.label ||
              "Dashboard"}
          </h2>

          <div className="flex items-center gap-3">
            <NotificationDropdown />
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
