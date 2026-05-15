import { useState, useEffect } from "react";
import { Video, Minus, Square, X } from "lucide-react";

export function TitleBar() {
  const isMac = window.electronAPI?.platform === "darwin";
  const [isMaximized, setIsMaximized] = useState(false);
  const controls = window.electronAPI?.windowControls;

  useEffect(() => {
    if (!controls) return;
    const check = () => controls.isMaximized().then(setIsMaximized);
    check();
    const id = setInterval(check, 300);
    return () => clearInterval(id);
  }, [controls]);

  if (isMac) {
    // macOS keeps native traffic lights; we just need a draggable strip
    return (
      <div className="h-8 w-full bg-surface-light dark:bg-surface-dark drag-region select-none" />
    );
  }

  return (
    <div className="h-10 w-full bg-surface-light dark:bg-surface-dark border-b border-border-light dark:border-border-dark flex items-center justify-between drag-region select-none shrink-0">
      <div className="pl-3 flex items-center gap-2 no-drag">
        <div className="w-6 h-6 rounded-md bg-primary flex items-center justify-center">
          <Video className="w-3.5 h-3.5 text-white" />
        </div>
      </div>

      <div className="flex items-center no-drag">
        <button
          onClick={() => controls?.minimize()}
          className="h-10 w-10 flex items-center justify-center text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
        >
          <Minus className="w-4 h-4" />
        </button>
        <button
          onClick={() => controls?.maximize()}
          className="h-10 w-10 flex items-center justify-center text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
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
          className="h-10 w-10 flex items-center justify-center text-gray-500 hover:bg-red-500 hover:text-white transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
