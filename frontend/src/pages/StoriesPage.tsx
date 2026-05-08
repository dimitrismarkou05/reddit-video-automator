import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Plus,
  RefreshCw,
  Link2,
  Film,
  ChevronDown,
  ChevronRight,
  MessageCircle,
  ArrowUp,
  Calendar,
  ExternalLink,
  BookOpen,
  X,
  Trash2,
  ChevronUp,
  AlertTriangle,
} from "lucide-react";
import { storyApi, subredditApi } from "@/services/api";
import { useNotificationStore } from "@/store";
import { notificationApi } from "@/services/api";
import { GenerateVideoModal } from "@/components/GenerateVideoModal";
import type { Story } from "@/types";
import { formatDistanceToNow } from "date-fns";
import toast from "react-hot-toast";

/* Subreddit Badge with delete */
function SubredditBadge({
  sub,
  onDelete,
}: {
  sub: { id: number; display_name: string };
  onDelete: (id: number, name: string) => void;
}) {
  return (
    <span className="group inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 text-primary text-sm rounded-full font-medium transition-colors hover:bg-primary/15">
      {sub.display_name}

      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete(sub.id, sub.display_name);
        }}
        className="
        cursor-pointer flex items-center justify-center
        w-5 h-5 rounded-full
        text-primary
        transition-all
        hover:bg-primary/20
        hover:text-primary-foreground
      "
        title={`Remove ${sub.display_name}`}
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </span>
  );
}

/* Expandable subreddit list */
function SubredditList({
  subreddits,
  onDelete,
  onDeleteAll,
}: {
  subreddits: { id: number; display_name: string }[];
  onDelete: (id: number, name: string) => void;
  onDeleteAll: () => void;
}) {
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

  const visibleCount = subreddits.length;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        {/* Scrollable / expandable container */}
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

          {/* Fade indicator when collapsed and overflowing */}
          {!expanded && overflows && (
            <div className="absolute right-0 top-0 bottom-0 w-16 bg-linear-to-l from-background-light dark:from-background-dark to-transparent pointer-events-none" />
          )}
        </div>

        {/* Toggle expand */}
        {visibleCount > 0 && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="cursor-pointer shrink-0 p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 transition-colors"
            title={expanded ? "Collapse list" : "Expand list"}
          >
            {expanded ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>
        )}

        {/* Delete all */}
        {visibleCount > 0 && (
          <button
            onClick={onDeleteAll}
            className="cursor-pointer shrink-0 p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-red-500 transition-colors"
            title="Delete all subreddits"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Overflow hint */}
      {!expanded && overflows && (
        <p className="text-xs text-gray-400">
          {visibleCount} subreddits — click the arrow to see all
        </p>
      )}
    </div>
  );
}

/* Story Card */
function StoryCard({ story, depth = 0 }: { story: Story; depth?: number }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const hasUpdates = story.updates && story.updates.length > 0;
  const hasVideo = !!story.generated_video;

  return (
    <div
      className={`${depth > 0 ? "ml-8 border-l-2 border-primary/20 pl-4" : ""}`}
    >
      <div className="card p-4 mb-3 hover:shadow-md transition-shadow">
        <div className="flex items-start gap-4">
          {hasUpdates && (
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="cursor-pointer mt-1 p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
            </button>
          )}

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2 py-0.5 bg-primary/10 text-primary text-xs rounded-full font-medium">
                r/{story.subreddit}
              </span>
              {story.is_update && (
                <span className="px-2 py-0.5 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 text-xs rounded-full font-medium">
                  Update
                </span>
              )}
              {hasVideo && (
                <span className="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 text-xs rounded-full font-medium flex items-center gap-1">
                  <Film className="w-3 h-3" />
                  Video Ready
                </span>
              )}
            </div>

            <h3 className="font-semibold text-base mb-1">{story.title}</h3>

            <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
              <span className="flex items-center gap-1">
                <ArrowUp className="w-3 h-3" />
                {story.score.toLocaleString()}
              </span>
              <span className="flex items-center gap-1">
                <MessageCircle className="w-3 h-3" />
                u/{story.author}
              </span>
              <span className="flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                {formatDistanceToNow(new Date(story.fetched_at), {
                  addSuffix: true,
                })}
              </span>
              {hasUpdates && (
                <span className="flex items-center gap-1 text-primary">
                  <Link2 className="w-3 h-3" />
                  {story.updates?.length} update
                  {story.updates?.length !== 1 ? "s" : ""}
                </span>
              )}
            </div>

            {story.body && (
              <p className="mt-2 text-sm text-gray-600 dark:text-gray-300 line-clamp-2">
                {story.body.substring(0, 200)}
                {story.body.length > 200 ? "..." : ""}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <button
              onClick={() => setShowGenerateModal(true)}
              disabled={hasVideo}
              className={`cursor-pointer p-2 rounded-lg transition-colors ${
                hasVideo
                  ? "bg-green-100 dark:bg-green-900/30 text-green-600 cursor-default"
                  : "bg-primary/10 text-primary hover:bg-primary/20"
              }`}
              title={hasVideo ? "Video already generated" : "Generate video"}
            >
              <Film className="w-5 h-5" />
            </button>
            <a
              href={story.permalink}
              target="_blank"
              rel="noopener noreferrer"
              className="p-2 rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
              title="View on Reddit"
            >
              <ExternalLink className="w-5 h-5" />
            </a>
          </div>
        </div>
      </div>

      {isExpanded && hasUpdates && (
        <div className="space-y-2">
          {story.updates?.map((update) => (
            <StoryCard key={update.id} story={update} depth={depth + 1} />
          ))}
        </div>
      )}

      {showGenerateModal && (
        <GenerateVideoModal
          story={story}
          onClose={() => setShowGenerateModal(false)}
        />
      )}
    </div>
  );
}

/* Delete Confirmation Modal */
function DeleteConfirmModal({
  title,
  message,
  warning,
  onConfirm,
  onCancel,
}: {
  title: string;
  message: string;
  warning?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-surface-light dark:bg-surface-dark rounded-2xl w-full max-w-md shadow-xl p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-red-500" />
          </div>
          <h3 className="text-lg font-semibold">{title}</h3>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-300 mb-2">
          {message}
        </p>
        {warning && (
          <p className="text-sm text-red-600 dark:text-red-400 mb-4 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg">
            {warning}
          </p>
        )}
        <div className="flex items-center justify-end gap-3">
          <button onClick={onCancel} className="cursor-pointer btn-secondary">
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="cursor-pointer px-4 py-2 bg-red-500 text-white rounded-lg font-medium hover:bg-red-600 transition-colors flex items-center gap-2"
          >
            <Trash2 className="w-4 h-4" />
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

/* Main Page */
export function StoriesPage() {
  const [newSubreddit, setNewSubreddit] = useState("");
  const [isAdding, setIsAdding] = useState(false);
  const { setNotifications } = useNotificationStore();

  /* Delete confirmation state */
  const [deleteTarget, setDeleteTarget] = useState<{
    type: "single" | "all";
    id?: number;
    name?: string;
  } | null>(null);

  const {
    data: stories,
    isLoading,
    refetch: refetchStories,
  } = useQuery({
    queryKey: ["stories"],
    queryFn: async () => {
      const { data } = await storyApi.list();
      return data.filter((s: Story) => !s.is_update);
    },
  });

  const { data: subreddits, refetch: refetchSubreddits } = useQuery({
    queryKey: ["subreddits"],
    queryFn: async () => {
      const { data } = await subredditApi.list();
      return data;
    },
  });

  const refreshNotifications = async () => {
    try {
      const { data } = await notificationApi.list(false, 20);
      setNotifications(data);
    } catch (e) {
      console.error("Failed to refresh notifications:", e);
    }
  };

  const handleAddSubreddit = async () => {
    if (!newSubreddit.trim()) return;
    setIsAdding(true);
    try {
      await subredditApi.add(newSubreddit.trim());
      toast.success(`Added r/${newSubreddit.trim()}`);
      setNewSubreddit("");
      refetchSubreddits();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to add subreddit");
    } finally {
      setIsAdding(false);
    }
  };

  const handleDeleteSubreddit = async (id: number) => {
    try {
      await subredditApi.delete(id);
      toast.success("Subreddit removed");
      refetchSubreddits();
      refetchStories();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to delete subreddit");
    }
  };

  const handleDeleteAllSubreddits = async () => {
    try {
      const { data } = await subredditApi.deleteAll();
      toast.success(`Deleted ${data.count} subreddit(s)`);
      refetchSubreddits();
      refetchStories();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Failed to delete all subreddits",
      );
    }
  };

  const handleFetchAll = async () => {
    toast.loading("Fetching stories...", { id: "fetch" });
    try {
      const { data } = await subredditApi.fetchAll();

      const errors = data.filter(
        (r: any) => r.error !== null && r.error !== undefined,
      );
      const successes = data.filter(
        (r: any) => !r.error && r.fetched_count > 0,
      );
      const empty = data.filter((r: any) => !r.error && r.fetched_count === 0);

      if (errors.length > 0) {
        const totalSubs = data.length;
        toast.error(
          `Fetch failed for ${errors.length} of ${totalSubs} subreddit(s). Check notification inbox for details.`,
          { id: "fetch", duration: 5000 },
        );
      } else if (successes.length > 0) {
        const total = successes.reduce(
          (sum: number, r: any) => sum + r.fetched_count,
          0,
        );
        toast.success(
          `Fetched ${total} new stories from ${successes.length} subreddit(s)`,
          { id: "fetch" },
        );
      } else if (empty.length > 0) {
        toast(`No new stories found in ${empty.length} subreddit(s)`, {
          id: "fetch",
          icon: "ℹ️",
        });
      } else {
        toast("Nothing to fetch — no active subreddits", { id: "fetch" });
      }

      await refreshNotifications();
      refetchStories();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Fetch request failed", {
        id: "fetch",
      });
    }
  };

  const handleLinkUpdates = async () => {
    try {
      toast.loading("Linking updates...", { id: "link" });
      await storyApi.linkUpdates();
      toast.success("Updates linked!", { id: "link" });
      await refreshNotifications();
      refetchStories();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Linking failed", { id: "link" });
    }
  };

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-0 flex items-center gap-2">
          <input
            type="text"
            value={newSubreddit}
            onChange={(e) => setNewSubreddit(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAddSubreddit()}
            placeholder="Add subreddit (e.g., AskReddit)"
            className="input max-w-xs"
          />
          <button
            onClick={handleAddSubreddit}
            disabled={isAdding}
            className="cursor-pointer btn-primary flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            Add
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleFetchAll}
            className="cursor-pointer btn-secondary flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Fetch All
          </button>
          <button
            onClick={handleLinkUpdates}
            className="cursor-pointer btn-secondary flex items-center gap-2"
          >
            <Link2 className="w-4 h-4" />
            Link Updates
          </button>
        </div>
      </div>

      {/* Subreddit list */}
      {subreddits && subreddits.length > 0 && (
        <SubredditList
          subreddits={subreddits}
          onDelete={(id, name) => setDeleteTarget({ type: "single", id, name })}
          onDeleteAll={() => setDeleteTarget({ type: "all" })}
        />
      )}

      {/* Stories */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      ) : stories && stories.length > 0 ? (
        <div className="space-y-2">
          {stories.map((story: Story) => (
            <StoryCard key={story.id} story={story} />
          ))}
        </div>
      ) : (
        <div className="card p-12 text-center">
          <BookOpen className="w-12 h-12 mx-auto mb-4 text-gray-300" />
          <h3 className="text-lg font-semibold text-gray-500">
            No stories yet
          </h3>
          <p className="text-sm text-gray-400 mt-1">
            Add a subreddit and click "Fetch All" to get started
          </p>
        </div>
      )}

      {/* Delete confirmation modal */}
      {deleteTarget?.type === "single" && (
        <DeleteConfirmModal
          title="Remove Subreddit?"
          message={`Are you sure you want to remove ${deleteTarget.name}? This will stop monitoring this subreddit.`}
          warning="All stories fetched from this subreddit will also be deleted. This action cannot be undone."
          onConfirm={() => {
            if (deleteTarget.id) handleDeleteSubreddit(deleteTarget.id);
            setDeleteTarget(null);
          }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {deleteTarget?.type === "all" && (
        <DeleteConfirmModal
          title="Delete All Subreddits?"
          message={`Are you sure you want to delete all ${subreddits?.length || 0} subreddits?`}
          warning="This will permanently delete all subreddits and every story fetched from them. This action cannot be undone."
          onConfirm={() => {
            handleDeleteAllSubreddits();
            setDeleteTarget(null);
          }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}
