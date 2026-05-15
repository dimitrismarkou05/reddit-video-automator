import { useState, useEffect, useRef } from "react";
import { useNavigate, useLocation, useNavigationType } from "react-router-dom";
import {
  Minus,
  Square,
  X,
  ChevronLeft,
  ChevronRight,
  BookOpen,
  Video,
  Settings,
  Bot,
} from "lucide-react";

const routeMeta: Record<string, { label: string; icon: typeof BookOpen }> = {
  "/stories": { label: "Stories", icon: BookOpen },
  "/videos": { label: "Videos", icon: Video },
  "/automation": { label: "Automation", icon: Bot },
  "/settings": { label: "Settings", icon: Settings },
  "/login": { label: "Log In", icon: Video },
  "/setup": { label: "API Setup", icon: Settings },
};

export function TitleBar() {
  const isMac = window.electronAPI?.platform === "darwin";
  const [isMaximized, setIsMaximized] = useState(false);
  const controls = window.electronAPI?.windowControls;
  const navigate = useNavigate();
  const location = useLocation();
  const navigationType = useNavigationType(); // "PUSH" | "REPLACE" | "POP"

  // Store the history of entry keys (unique per session entry)
  const stackRef = useRef<string[]>([]);
  // Current position in that stack
  const indexRef = useRef(-1);

  const [canGoBack, setCanGoBack] = useState(false);
  const [canGoForward, setCanGoForward] = useState(false);

  // Sync the UI state from the refs
  const sync = () => {
    setCanGoBack(indexRef.current > 0);
    setCanGoForward(
      indexRef.current >= 0 && indexRef.current < stackRef.current.length - 1,
    );
  };

  // Initialise the stack on first render
  useEffect(() => {
    if (stackRef.current.length === 0) {
      stackRef.current = [location.key];
      indexRef.current = 0;
      sync();
    }
  }, []);

  // Keep the stack in sync with every navigation
  useEffect(() => {
    const key = location.key;
    const stack = stackRef.current;
    let idx = indexRef.current;

    switch (navigationType) {
      case "PUSH": {
        // Truncate anything after current index, then add new entry
        const newStack = stack.slice(0, idx + 1);
        newStack.push(key);
        stackRef.current = newStack;
        indexRef.current = newStack.length - 1;
        break;
      }
      case "REPLACE": {
        // Replace current entry, length stays the same
        stack[idx] = key;
        stackRef.current = [...stack]; // ensure new reference for state update if needed
        break;
      }
      case "POP": {
        // Find the index of the popped entry in our stack
        const newIdx = stack.indexOf(key);
        if (newIdx !== -1) {
          indexRef.current = newIdx;
        } else {
          // Fallback: should never happen in normal use, reset stack
          stackRef.current = [key];
          indexRef.current = 0;
        }
        break;
      }
    }
    sync();
  }, [location.key, navigationType]);

  // Keep window maximised state in sync (unchanged)
  useEffect(() => {
    if (!controls) return;
    const check = () => controls.isMaximized().then(setIsMaximized);
    check();
    const id = setInterval(check, 300);
    return () => clearInterval(id);
  }, [controls]);

  // Now just delegate to the browser history
  const handleBack = () => {
    if (!canGoBack) return;
    navigate(-1);
  };

  const handleForward = () => {
    if (!canGoForward) return;
    navigate(1);
  };

  const meta = routeMeta[location.pathname];
  const CurrentIcon = meta?.icon;
  const title =
    meta?.label ||
    location.pathname.replace("/", "") ||
    "Reddit Video Automator";

  const isLogin = location.pathname === "/login";

  if (isMac) {
    return (
      <div className="h-7 w-full bg-surface-light dark:bg-surface-dark drag-region select-none flex items-center justify-center">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
          {title}
        </span>
      </div>
    );
  }

  return (
    <div className="h-9 w-full bg-surface-light dark:bg-surface-dark border-b border-border-light dark:border-border-dark flex items-center justify-between drag-region select-none shrink-0">
      {/* Left: Navigation */}
      <div className="flex items-center gap-1 no-drag pl-2">
        <button
          onClick={handleBack}
          disabled={!canGoBack}
          className="h-7 w-7 flex items-center justify-center rounded-md text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-30 disabled:hover:bg-transparent"
          title="Back"
        >
          <ChevronLeft className="w-4.5 h-4.5" />
        </button>
        <button
          onClick={handleForward}
          disabled={!canGoForward}
          className="h-7 w-7 flex items-center justify-center rounded-md text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-30 disabled:hover:bg-transparent"
          title="Forward"
        >
          <ChevronRight className="w-4.5 h-4.5" />
        </button>
      </div>

      {/* Center: Title with icon */}
      <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-1.5 pointer-events-none">
        {isLogin ? (
          <div className="w-5 h-5 rounded-sm bg-primary flex items-center justify-center">
            <Video className="w-3.5 h-3.5 text-white" />
          </div>
        ) : CurrentIcon ? (
          <CurrentIcon className="w-4.5 h-4.5 text-gray-700 dark:text-gray-300" />
        ) : null}
        <span className="text-[13px] font-semibold text-gray-700 dark:text-gray-300">
          {title}
        </span>
      </div>

      {/* Right: Window controls */}
      <div className="flex items-center no-drag">
        <button
          onClick={() => controls?.minimize()}
          className="h-9 w-10 flex items-center justify-center text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
        >
          <Minus className="w-4 h-4" />
        </button>
        <button
          onClick={() => controls?.maximize()}
          className="h-9 w-10 flex items-center justify-center text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
        >
          {isMaximized ? (
            <svg
              className="w-3.5 h-3.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <rect x="5" y="9" width="10" height="10" rx="1" />
              <path d="M9 5h10v10" />
            </svg>
          ) : (
            <Square className="w-3.5 h-3.5" />
          )}
        </button>
        <button
          onClick={() => controls?.close()}
          className="h-9 w-10 flex items-center justify-center text-gray-500 hover:bg-red-500 hover:text-white transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
