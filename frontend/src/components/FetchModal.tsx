import { useState, useRef, useEffect } from "react";
import { X, RefreshCw, ChevronDown, Zap, Info } from "lucide-react";
import { subredditApi } from "@/services/api";
import type { Subreddit } from "@/types";
import toast from "react-hot-toast";

interface FetchModalProps {
  subreddits: Subreddit[];
  onClose: () => void;
  onFetchComplete: () => void;
}

const SORT_OPTIONS = [
  { value: "top", label: "Most Upvoted" },
  { value: "new", label: "Newest" },
];

const TIME_FILTER_OPTIONS = [
  { value: "day", label: "Today" },
  { value: "week", label: "This Week" },
  { value: "month", label: "This Month" },
  { value: "year", label: "This Year" },
  { value: "all", label: "All Time" },
];

const LIMIT_OPTIONS = [5, 10, 15, 20, 25];

export function FetchModal({
  subreddits,
  onClose,
  onFetchComplete,
}: FetchModalProps) {
  const [selectedSubreddit, setSelectedSubreddit] = useState<string>("all");
  const [sort, setSort] = useState<string>("top");
  const [timeFilter, setTimeFilter] = useState<string>("week");
  const [limit, setLimit] = useState<number>(25);
  const [isFetching, setIsFetching] = useState(false);
  const [showRateLimitWarning, setShowRateLimitWarning] = useState<{
    requests_remaining: number;
    requests_needed: number;
    partial_story_count: number;
    reset_in_seconds: number;
  } | null>(null);
  const [showSubredditDropdown, setShowSubredditDropdown] = useState(false);
  const subredditDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
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

  const isTimeFilterDisabled = sort === "new";

  const handleFetch = async (skipRateLimitCheck = false) => {
    if (isFetching) return;

    if (!skipRateLimitCheck) {
      try {
        const { data: preview } = await subredditApi.fetchPreview();
        if (preview.will_be_exhausted) {
          setShowRateLimitWarning({
            requests_remaining: preview.requests_remaining,
            requests_needed: preview.requests_needed,
            partial_story_count: preview.partial_story_count,
            reset_in_seconds: preview.reset_in_seconds,
          });
          return;
        }
      } catch (e) {
        // Preview endpoint might not exist, proceed anyway
      }
    }

    setIsFetching(true);
    setShowRateLimitWarning(null);

    const subredditId =
      selectedSubreddit === "all" ? null : parseInt(selectedSubreddit);

    try {
      const { data } = await subredditApi.fetchWithParams({
        subreddit_id: subredditId,
        sort,
        time_filter: sort === "top" ? timeFilter : "week",
        limit,
      });

      const errors = data.filter((r: any) => r.error != null);
      const successes = data.filter(
        (r: any) => !r.error && r.fetched_count > 0,
      );
      const empty = data.filter((r: any) => !r.error && r.fetched_count === 0);

      if (errors.length > 0) {
        const rateLimitError = errors.find((r: any) =>
          r.error?.toLowerCase().includes("rate limit"),
        );
        if (rateLimitError) {
          const resetMatch = rateLimitError.error.match(/(\d+) seconds/);
          const resetMinutes = resetMatch
            ? Math.ceil(parseInt(resetMatch[1]) / 60)
            : "a few";
          toast.error(
            `Rate limit reached. Wait ~${resetMinutes} minutes before retrying.`,
            { duration: 8000 },
          );
        } else if (errors.length === 1) {
          toast.error(`Failed to fetch r/${errors[0].subreddit}`, {
            duration: 5000,
          });
        } else {
          const subWord = errors.length === 1 ? "subreddit" : "subreddits";
          toast.error(`Failed to fetch ${errors.length} ${subWord}`, {
            duration: 5000,
          });
        }
      } else if (successes.length > 0) {
        const total = successes.reduce(
          (s: number, r: any) => s + r.fetched_count,
          0,
        );
        const storyWord = total === 1 ? "story" : "stories";
        const subWord = successes.length === 1 ? "subreddit" : "subreddits";
        if (successes.length === 1) {
          toast.success(
            `Fetched ${total} ${storyWord} from r/${successes[0].subreddit}`,
          );
        } else {
          toast.success(
            `Fetched ${total} ${storyWord} from ${successes.length} ${subWord}`,
          );
        }
      } else if (empty.length > 0) {
        if (empty.length === 1) {
          toast(`No new stories found in r/${empty[0].subreddit}`);
        } else {
          const subWord = empty.length === 1 ? "subreddit" : "subreddits";
          toast(`No new stories found in ${empty.length} ${subWord}`);
        }
      } else {
        toast("No active subreddits to fetch stories", {
          id: "fetch",
          icon: <Info className="w-5 h-5 text-blue-500" />,
        });
      }

      onFetchComplete();
      onClose();
    } catch (e: any) {
      if (e.response?.status === 429) {
        const detail = e.response?.data?.detail || "Rate limit reached";
        const resetMatch = detail.match(/(\d+) seconds/);
        const resetMinutes = resetMatch
          ? Math.ceil(parseInt(resetMatch[1]) / 60)
          : "a few";
        toast.error(
          `Rate limit reached. Wait ~${resetMinutes} minutes before retrying.`,
          { duration: 8000 },
        );
      } else {
        toast.error(e.response?.data?.detail || "Failed to fetch stories");
      }
    } finally {
      setIsFetching(false);
    }
  };

  const handleConfirmRateLimit = () => {
    setShowRateLimitWarning(null);
    handleFetch(true);
  };

  const selectedSubredditName =
    selectedSubreddit === "all"
      ? "All Subreddits"
      : subreddits?.find((s) => s.id === parseInt(selectedSubreddit))
          ?.display_name || selectedSubreddit;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-surface-light dark:bg-surface-dark rounded-2xl w-full max-w-md shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border-light dark:border-border-dark">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
              <RefreshCw className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Fetch Stories</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Configure fetch parameters
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={isFetching}
            className="cursor-pointer p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-white/5 "
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-5">
          {isFetching ? (
            <div className="text-center py-8">
              <div className="relative w-16 h-16 mx-auto mb-4">
                <div className="absolute inset-0 rounded-full border-4 border-primary/20" />
                <div className="absolute inset-0 rounded-full border-4 border-primary border-t-transparent animate-spin" />
                <RefreshCw className="absolute inset-0 m-auto w-6 h-6 text-primary" />
              </div>
              <h3 className="text-lg font-semibold mb-2">
                Fetching Stories...
              </h3>
              <p className="text-sm text-gray-500">
                This may take a moment depending on the number of subreddits.
              </p>
            </div>
          ) : showRateLimitWarning ? (
            <RateLimitWarning
              preview={showRateLimitWarning}
              onConfirm={handleConfirmRateLimit}
              onCancel={() => setShowRateLimitWarning(null)}
            />
          ) : (
            <>
              {/* Subreddit Selection — custom dropdown matching StoryFilters style */}
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Subreddit
                </label>
                <div className="relative" ref={subredditDropdownRef}>
                  <button
                    onClick={() => setShowSubredditDropdown((v) => !v)}
                    className="cursor-pointer w-full flex items-center gap-2 px-3 py-2 bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-white/5 "
                  >
                    <span className="flex-1 text-left">
                      {selectedSubredditName}
                    </span>
                    <ChevronDown
                      className={`w-3 h-3 text-gray-400 transition-transform ${showSubredditDropdown ? "rotate-180" : ""}`}
                    />
                  </button>
                  {showSubredditDropdown && (
                    <div className="absolute left-0 top-full mt-1 w-full bg-surface-light dark:bg-surface-dark rounded-xl shadow-lg border border-border-light dark:border-border-dark z-50 overflow-hidden">
                      <button
                        onClick={() => {
                          setSelectedSubreddit("all");
                          setShowSubredditDropdown(false);
                        }}
                        className={`cursor-pointer w-full flex items-center gap-3 px-4 py-2.5 text-sm  ${
                          selectedSubreddit === "all"
                            ? "bg-primary/10 text-primary font-medium"
                            : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5"
                        }`}
                      >
                        All Subreddits
                      </button>
                      {subreddits.map((sub) => (
                        <button
                          key={sub.id}
                          onClick={() => {
                            setSelectedSubreddit(String(sub.id));
                            setShowSubredditDropdown(false);
                          }}
                          className={`cursor-pointer w-full flex items-center gap-3 px-4 py-2.5 text-sm  ${
                            selectedSubreddit === String(sub.id)
                              ? "bg-primary/10 text-primary font-medium"
                              : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5"
                          }`}
                        >
                          {sub.display_name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Number of Stories */}
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Number of Stories
                </label>
                <div className="grid grid-cols-5 gap-2">
                  {LIMIT_OPTIONS.map((num) => (
                    <button
                      key={num}
                      onClick={() => setLimit(num)}
                      className={`cursor-pointer py-2 rounded-lg text-sm font-medium  ${
                        limit === num
                          ? "bg-primary text-white"
                          : "bg-gray-100 dark:bg-[#2a2a2a] text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-border-dark"
                      }`}
                    >
                      {num}
                    </button>
                  ))}
                </div>
              </div>

              {/* Sort Type */}
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Sort By
                </label>
                <div className="relative">
                  <select
                    value={sort}
                    onChange={(e) => setSort(e.target.value)}
                    className="input appearance-none pr-10"
                  >
                    {SORT_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                </div>
              </div>

              {/* Time Filter - only for "top" */}
              <div className="space-y-2">
                <label
                  className={`block text-sm font-medium ${
                    isTimeFilterDisabled
                      ? "text-gray-400 dark:text-gray-600"
                      : "text-gray-700 dark:text-gray-300"
                  }`}
                >
                  Time Period
                  {isTimeFilterDisabled && (
                    <span className="text-xs ml-2 text-gray-400">
                      (only for Most Upvoted)
                    </span>
                  )}
                </label>
                <div className="relative">
                  <select
                    value={timeFilter}
                    onChange={(e) => setTimeFilter(e.target.value)}
                    disabled={isTimeFilterDisabled}
                    className={`input appearance-none pr-10 transition-opacity ${
                      isTimeFilterDisabled
                        ? "opacity-50 cursor-not-allowed bg-gray-100 dark:bg-[#2a2a2a]"
                        : ""
                    }`}
                  >
                    {TIME_FILTER_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        {!isFetching && !showRateLimitWarning && (
          <div className="flex items-center justify-end gap-3 p-6 border-t border-border-light dark:border-border-dark">
            <button onClick={onClose} className="cursor-pointer btn-secondary">
              Cancel
            </button>
            <button
              onClick={() => handleFetch()}
              className="cursor-pointer btn-primary flex items-center gap-2"
            >
              <RefreshCw className="w-4 h-4" />
              Fetch Stories
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function RateLimitWarning({
  preview,
  onConfirm,
  onCancel,
}: {
  preview: {
    requests_remaining: number;
    requests_needed: number;
    partial_story_count: number;
    reset_in_seconds: number;
  };
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const canPartialFetch = preview.partial_story_count > 0;
  const resetMinutes = Math.ceil(preview.reset_in_seconds / 60);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-yellow-100 dark:bg-yellow-900/30 flex items-center justify-center">
          <Zap className="w-5 h-5 text-yellow-600" />
        </div>
        <h3 className="text-lg font-semibold">Rate Limit Warning</h3>
      </div>

      <p className="text-sm text-gray-600 dark:text-gray-300">
        You are close to Reddit's rate limit. This fetch will exhaust your
        remaining requests.
      </p>

      <div className="bg-gray-50 dark:bg-surface-dark/50 rounded-lg p-3 space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Requests remaining:</span>
          <span className="font-medium text-yellow-600">
            {preview.requests_remaining}
          </span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Requests needed:</span>
          <span className="font-medium">{preview.requests_needed}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Limit resets in:</span>
          <span className="font-medium">
            ~{resetMinutes} minute{resetMinutes !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {canPartialFetch ? (
        <p className="text-sm text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/20 p-3 rounded-lg">
          Only{" "}
          <strong>
            {preview.partial_story_count}{" "}
            {preview.partial_story_count === 1 ? "story" : "stories"}
          </strong>{" "}
          can be fetched before hitting the limit.
        </p>
      ) : (
        <p className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg">
          This request will fully exhaust your rate limit. You'll need to wait ~
          {resetMinutes} minute{resetMinutes !== 1 ? "s" : ""} before fetching
          again.
        </p>
      )}

      <div className="flex items-center justify-end gap-3 pt-2">
        <button onClick={onCancel} className="cursor-pointer btn-secondary">
          Cancel
        </button>
        <button
          onClick={onConfirm}
          className="cursor-pointer btn-primary flex items-center gap-2"
        >
          <Zap className="w-4 h-4" />
          {canPartialFetch
            ? `Fetch ${preview.partial_story_count} ${preview.partial_story_count === 1 ? "Story" : "Stories"}`
            : "Fetch Anyway"}
        </button>
      </div>
    </div>
  );
}
