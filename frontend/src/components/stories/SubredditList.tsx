import { useState, useRef, useEffect } from "react";
import { ChevronDown, ChevronUp, Trash2 } from "lucide-react";
import { SubredditBadge } from "./SubredditBadge";

interface SubredditListProps {
  subreddits: { id: number; display_name: string }[];
  onDelete: (id: number, name: string) => void;
  onDeleteAll: () => void;
}

export function SubredditList({
  subreddits,
  onDelete,
  onDeleteAll,
}: SubredditListProps) {
  const [expanded, setExpanded] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [overflows, setOverflows] = useState(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const check = () => setOverflows(el.scrollWidth > el.clientWidth);
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    window.addEventListener("resize", check);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", check);
    };
  }, [subreddits]);

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <div
          ref={containerRef}
          className={`relative flex-1 min-w-0 ${
            expanded
              ? "flex flex-wrap gap-2"
              : "flex items-center gap-2 overflow-hidden"
          }`}
        >
          {subreddits.map((sub) => (
            <SubredditBadge key={sub.id} sub={sub} onDelete={onDelete} />
          ))}
          {!expanded && overflows && (
            <div className="absolute right-0 top-0 bottom-0 w-16 bg-linear-to-l from-background-light dark:from-background-dark to-transparent pointer-events-none" />
          )}
        </div>
        {subreddits.length > 0 && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="cursor-pointer shrink-0 p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-white/5 text-gray-500 "
            title={expanded ? "Collapse" : "Expand"}
          >
            {expanded ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>
        )}
        {subreddits.length > 0 && (
          <button
            onClick={onDeleteAll}
            className="cursor-pointer shrink-0 p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-red-500 "
            title="Delete all subreddits"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>
      {!expanded && overflows && (
        <p className="text-xs text-gray-400">
          {subreddits.length} subreddits — click arrow to see all
        </p>
      )}
    </div>
  );
}
