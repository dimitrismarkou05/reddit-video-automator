import { useRef, useEffect } from "react";
import { Filter, ArrowUpDown, ChevronDown, Trash } from "lucide-react";
import { SORT_OPTIONS, type SortOption } from "@/config/sortOptions";

interface StoryFiltersProps {
  subreddits: any[];
  selectedSubreddit: string;
  onSelectSubreddit: (name: string) => void;
  sortBy: SortOption;
  onSelectSort: (sort: SortOption) => void;
  showSubredditDropdown: boolean;
  onToggleSubredditDropdown: () => void;
  showSortDropdown: boolean;
  onToggleSortDropdown: () => void;
  onDeleteAllStories: () => void;
  setShowSubredditDropdown: (value: boolean) => void;
  setShowSortDropdown: (value: boolean) => void;
}

export function StoryFilters({
  subreddits,
  selectedSubreddit,
  onSelectSubreddit,
  sortBy,
  onSelectSort,
  showSubredditDropdown,
  onToggleSubredditDropdown,
  showSortDropdown,
  onToggleSortDropdown,
  onDeleteAllStories,
  setShowSubredditDropdown,
  setShowSortDropdown,
}: StoryFiltersProps) {
  const subredditDropdownRef = useRef<HTMLDivElement>(null);
  const sortDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (
        sortDropdownRef.current &&
        !sortDropdownRef.current.contains(e.target as Node)
      ) {
        setShowSortDropdown(false);
      }
      if (
        subredditDropdownRef.current &&
        !subredditDropdownRef.current.contains(e.target as Node)
      ) {
        setShowSubredditDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const activeSortLabel = SORT_OPTIONS.find((s) => s.value === sortBy)?.label;

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="relative" ref={subredditDropdownRef}>
        <button
          onClick={onToggleSubredditDropdown}
          className="cursor-pointer flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-white/5 "
        >
          <Filter className="w-4 h-4" />
          {selectedSubreddit === "all"
            ? "All Subreddits"
            : subreddits?.find((s: any) => s.name === selectedSubreddit)
                ?.display_name || selectedSubreddit}
          <ChevronDown className="w-3 h-3" />
        </button>
        {showSubredditDropdown && (
          <div className="absolute left-0 top-full mt-1 w-56 bg-surface-light dark:bg-surface-dark rounded-xl shadow-lg border border-border-light dark:border-border-dark z-50 overflow-hidden">
            <button
              onClick={() => {
                onSelectSubreddit("all");
              }}
              className={`cursor-pointer w-full flex items-center gap-3 px-4 py-2.5 text-sm  ${
                selectedSubreddit === "all"
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5"
              }`}
            >
              <Filter className="w-4 h-4" />
              All Subreddits
            </button>
            {subreddits?.map((sub: any) => (
              <button
                key={sub.id}
                onClick={() => {
                  onSelectSubreddit(sub.name);
                }}
                className={`cursor-pointer w-full flex items-center gap-3 px-4 py-2.5 text-sm  ${
                  selectedSubreddit === sub.name
                    ? "bg-primary/10 text-primary font-medium"
                    : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5"
                }`}
              >
                <span className="w-4 h-4 flex items-center justify-center text-xs font-medium text-gray-500">
                  r/
                </span>
                {sub.display_name}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="relative" ref={sortDropdownRef}>
        <button
          onClick={onToggleSortDropdown}
          className="cursor-pointer flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-white/5 "
        >
          <ArrowUpDown className="w-4 h-4" />
          {activeSortLabel}
          <ChevronDown className="w-3 h-3" />
        </button>
        {showSortDropdown && (
          <div className="absolute left-0 top-full mt-1 w-56 bg-surface-light dark:bg-surface-dark rounded-xl shadow-lg border border-border-light dark:border-border-dark z-50 overflow-hidden">
            {SORT_OPTIONS.map((option) => {
              const Icon = option.icon;
              return (
                <button
                  key={option.value}
                  onClick={() => {
                    onSelectSort(option.value);
                  }}
                  className={`cursor-pointer w-full flex items-center gap-3 px-4 py-2.5 text-sm  ${
                    sortBy === option.value
                      ? "bg-primary/10 text-primary font-medium"
                      : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {option.label}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {selectedSubreddit !== "all" && (
        <button
          onClick={() => onSelectSubreddit("all")}
          className="cursor-pointer text-sm text-primary hover:underline"
        >
          Clear filter
        </button>
      )}

      <div className="flex-1 flex justify-end">
        <button
          onClick={onDeleteAllStories}
          className="cursor-pointer flex items-center gap-2 px-3 py-1.5 text-sm text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg "
          title="Delete all stories"
        >
          <Trash className="w-4 h-4" />
          Delete All Stories
        </button>
      </div>
    </div>
  );
}
