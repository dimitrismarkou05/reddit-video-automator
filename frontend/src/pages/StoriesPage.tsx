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
  Filter,
  ArrowUpDown,
  ArrowDownAZ,
  Trash,
  Info,
  GitBranch,
  Clock,
} from "lucide-react";
import { storyApi, subredditApi } from "@/services/api";
import { useNotificationStore } from "@/store";
import { notificationApi } from "@/services/api";
import { GenerateVideoModal } from "@/components/GenerateVideoModal";
import { FetchModal } from "@/components/FetchModal";
import type { Story } from "@/types";
import { formatDistanceToNow, parseISO } from "date-fns";
import toast from "react-hot-toast";

type SortOption =
  | "date_desc"
  | "date_asc"
  | "score_desc"
  | "score_asc"
  | "title_asc";

const SORT_OPTIONS = [
  {
    value: "date_desc" as SortOption,
    label: "Newest first",
    icon: ArrowUpDown,
  },
  { value: "date_asc" as SortOption, label: "Oldest first", icon: ArrowUpDown },
  {
    value: "score_desc" as SortOption,
    label: "Upvotes: High → Low",
    icon: ArrowUpDown,
  },
  {
    value: "score_asc" as SortOption,
    label: "Upvotes: Low → High",
    icon: ArrowUpDown,
  },
  {
    value: "title_asc" as SortOption,
    label: "Alphabetical",
    icon: ArrowDownAZ,
  },
];

/* Parse UTC ISO string from backend */
function formatUtcRelative(dateString: string | null): string {
  if (!dateString) return "Unknown";
  try {
    const date = parseISO(dateString);
    return formatDistanceToNow(date, { addSuffix: true });
  } catch {
    return "Unknown";
  }
}

/* Strip "Update:" or "Update N:" prefix from title */
function stripUpdatePrefix(title: string): string {
  return title.replace(/^Update\s*(?:\d+)?\s*:\s*/i, "").trim();
}

/* Subreddit Badge */
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
        className="cursor-pointer flex items-center justify-center w-5 h-5 rounded-full text-primary transition-all hover:bg-primary/20 hover:text-primary-foreground"
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

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <div
          ref={containerRef}
          className={`relative flex-1 min-w-0 ${expanded ? "flex flex-wrap gap-2" : "flex items-center gap-2 overflow-hidden"}`}
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
            className="cursor-pointer shrink-0 p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 transition-colors"
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
            className="cursor-pointer shrink-0 p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-red-500 transition-colors"
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

function BranchConnector({ index, total }: { index: number; total: number }) {
  const isLast = index === total - 1;

  return (
    <div
      className="relative flex flex-col items-start"
      style={{ width: "36px", minWidth: "36px" }}
    >
      {/* Top vertical line */}
      <div
        className="absolute w-0.5 bg-gray-400 dark:bg-gray-500"
        style={{
          left: "11px",
          height: index === 0 ? "82px" : "70px",
          top: index === 0 ? "-12px" : "0",
        }}
      />

      {/* Rounded elbow + horizontal stub */}
      <div
        className="relative w-full"
        style={{ height: "20px", marginTop: "68px" }}
      >
        <svg
          className="absolute"
          style={{ left: "11px", top: "0px", width: "24px", height: "16px" }}
          viewBox="0 0 24 16"
          fill="none"
        >
          <path
            d="M 1 0 L 1 4 C 1 8, 4 10, 8 10 L 24 10"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            className="text-gray-400 dark:text-gray-500"
          />
        </svg>
      </div>

      {/* Bottom vertical line */}
      {!isLast && (
        <div
          className="w-0.5 flex-1 bg-gray-400 dark:bg-gray-500"
          style={{ marginLeft: "11px", marginTop: "2px" }}
        />
      )}
    </div>
  );
}

/* Update Card */
function UpdateCard({
  update,
  index,
  totalUpdates,
  onDelete,
}: {
  update: Story;
  index: number;
  totalUpdates: number;
  onDelete: (story: Story) => void;
}) {
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const hasVideo = !!update.generated_video;
  const showNumberBadge = totalUpdates > 1;
  const updateNumber = index + 1;
  const cleanTitle = stripUpdatePrefix(update.title);

  return (
    <div className="flex">
      {/* Branch connector */}
      <BranchConnector index={index} total={totalUpdates} />

      {/* Update card */}
      <div className="flex-1 pb-3">
        <div className="card p-4 hover:shadow-md transition-shadow">
          <div className="flex items-start gap-4">
            <div className="flex-1 min-w-0">
              {/* Badges */}
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <span className="px-2 py-0.5 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 text-xs rounded-full font-medium flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  Update
                </span>
                {showNumberBadge && (
                  <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 text-xs rounded-full font-medium">
                    #{updateNumber}
                  </span>
                )}
                {hasVideo && (
                  <span className="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 text-xs rounded-full font-medium flex items-center gap-1">
                    <Film className="w-3 h-3" />
                    Video Ready
                  </span>
                )}
              </div>

              {/* Title — stripped of "Update:" prefix */}
              <h3 className="font-semibold text-base mb-1">{cleanTitle}</h3>

              {/* Meta */}
              <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400 flex-wrap">
                <span className="flex items-center gap-1">
                  <ArrowUp className="w-3 h-3" />
                  {update.score.toLocaleString()}
                </span>
                <span className="flex items-center gap-1">
                  <MessageCircle className="w-3 h-3" />
                  u/{update.author}
                </span>
                <span className="flex items-center gap-1">
                  <Calendar className="w-3 h-3" />
                  {formatUtcRelative(update.created_utc)}
                </span>
              </div>

              {/* Body */}
              {update.body && (
                <p className="mt-2 text-sm text-gray-600 dark:text-gray-300 line-clamp-2">
                  {update.body.substring(0, 200)}
                  {update.body.length > 200 ? "..." : ""}
                </p>
              )}
            </div>

            {/* Actions */}
            <div className="flex flex-col gap-2">
              <button
                onClick={() => setShowGenerateModal(true)}
                disabled={hasVideo}
                className={`cursor-pointer p-2 rounded-lg transition-colors ${hasVideo ? "bg-green-100 dark:bg-green-900/30 text-green-600 cursor-default" : "bg-primary/10 text-primary hover:bg-primary/20"}`}
                title={hasVideo ? "Video ready" : "Generate video"}
              >
                <Film className="w-5 h-5" />
              </button>
              <a
                href={update.permalink}
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                title="View on Reddit"
              >
                <ExternalLink className="w-5 h-5" />
              </a>
              <button
                onClick={() => onDelete(update)}
                className="cursor-pointer p-2 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
                title="Delete update"
              >
                <Trash2 className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {showGenerateModal && (
        <GenerateVideoModal
          story={update}
          onClose={() => setShowGenerateModal(false)}
        />
      )}
    </div>
  );
}

/* Story Card */
function StoryCard({
  story,
  onDelete,
}: {
  story: Story;
  onDelete: (story: Story) => void;
}) {
  const [showUpdates, setShowUpdates] = useState(false);
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const hasUpdates = story.updates && story.updates.length > 0;
  const hasVideo = !!story.generated_video;
  const updateCount = story.updates?.length || 0;

  return (
    <div className="space-y-0">
      {/* Original Story Card */}
      <div className="card p-4 hover:shadow-md transition-shadow">
        <div className="flex items-start gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
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
              {hasUpdates && (
                <>
                  <span className="px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 text-xs rounded-full font-medium flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {updateCount} update{updateCount !== 1 ? "s" : ""}
                  </span>
                  <button
                    onClick={() => setShowUpdates(!showUpdates)}
                    className="cursor-pointer -ml-0.5 p-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors shrink-0 inline-flex items-center gap-0.5"
                    title={
                      showUpdates
                        ? "Hide updates"
                        : `Show ${updateCount} update${updateCount !== 1 ? "s" : ""}`
                    }
                  >
                    {showUpdates ? (
                      <ChevronDown className="w-3.5 h-3.5" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5" />
                    )}
                    <GitBranch className="w-3 h-3 text-primary" />
                  </button>
                </>
              )}
            </div>
            <h3 className="font-semibold text-base mb-1">{story.title}</h3>
            <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400 flex-wrap">
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
                {formatUtcRelative(story.created_utc)}
              </span>
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
              className={`cursor-pointer p-2 rounded-lg transition-colors ${hasVideo ? "bg-green-100 dark:bg-green-900/30 text-green-600 cursor-default" : "bg-primary/10 text-primary hover:bg-primary/20"}`}
              title={hasVideo ? "Video ready" : "Generate video"}
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
            <button
              onClick={() => onDelete(story)}
              className="cursor-pointer p-2 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
              title="Delete story"
            >
              <Trash2 className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Updates Section indented with branch lines */}
      {showUpdates && hasUpdates && (
        <div className="pl-4 pt-3">
          <div className="space-y-0">
            {story.updates?.map((update, index) => (
              <UpdateCard
                key={update.id}
                update={update}
                index={index}
                totalUpdates={updateCount}
                onDelete={onDelete}
              />
            ))}
          </div>
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

/* Private Subreddit Confirmation Modal */
function PrivateSubConfirmModal({
  name,
  message,
  onConfirm,
  onCancel,
}: {
  name: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-surface-light dark:bg-surface-dark rounded-2xl w-full max-w-md shadow-xl p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
            <Info className="w-5 h-5 text-blue-500" />
          </div>
          <h3 className="text-lg font-semibold">Private Subreddit: {name}</h3>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-300 mb-2">
          {message}
        </p>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          You won't be able to fetch stories from this subreddit unless you're a
          member. Add it anyway?
        </p>
        <div className="flex items-center justify-end gap-3">
          <button onClick={onCancel} className="cursor-pointer btn-secondary">
            Cancel
          </button>
          <button onClick={onConfirm} className="cursor-pointer btn-primary">
            Add Anyway
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

  const [selectedSubreddit, setSelectedSubreddit] = useState<string>("all");
  const [sortBy, setSortBy] = useState<SortOption>("date_desc");
  const [showSortDropdown, setShowSortDropdown] = useState(false);
  const sortDropdownRef = useRef<HTMLDivElement>(null);

  const [showSubredditDropdown, setShowSubredditDropdown] = useState(false);
  const subredditDropdownRef = useRef<HTMLDivElement>(null);

  const [showFetchModal, setShowFetchModal] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<
    | { type: "single"; id?: number; name?: string }
    | { type: "all" }
    | { type: "story"; story: Story }
    | { type: "all_stories" }
    | null
  >(null);

  const [privateSubConfirm, setPrivateSubConfirm] = useState<{
    name: string;
    message: string;
  } | null>(null);

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const STORIES_PER_PAGE = 10;

  const {
    data: stories,
    isLoading,
    refetch: refetchStories,
  } = useQuery({
    queryKey: ["stories", selectedSubreddit, sortBy],
    queryFn: async () => {
      const params: Record<string, any> = { sort_by: sortBy };
      if (selectedSubreddit !== "all") params.subreddit = selectedSubreddit;
      const { data } = await storyApi.list(params);
      return data;
    },
  });

  const { data: subreddits, refetch: refetchSubreddits } = useQuery({
    queryKey: ["subreddits"],
    queryFn: async () => {
      const { data } = await subredditApi.list();
      return data;
    },
  });

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (
        sortDropdownRef.current &&
        !sortDropdownRef.current.contains(e.target as Node)
      )
        setShowSortDropdown(false);
      if (
        subredditDropdownRef.current &&
        !subredditDropdownRef.current.contains(e.target as Node)
      )
        setShowSubredditDropdown(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Reset to first page when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [selectedSubreddit, sortBy]);

  const refreshNotifications = async () => {
    try {
      const { data } = await notificationApi.list(false, 20);
      setNotifications(data);
    } catch (e) {}
  };

  const handleAddSubreddit = async (forceAdd = false) => {
    if (!newSubreddit.trim()) return;
    setIsAdding(true);
    try {
      await subredditApi.add(newSubreddit.trim(), undefined, forceAdd);
      toast.success(`Added ${newSubreddit.trim()}`);
      setNewSubreddit("");
      refetchSubreddits();
    } catch (e: any) {
      const detail = e.response?.data?.detail;

      if (
        detail &&
        typeof detail === "object" &&
        detail.is_private &&
        !forceAdd
      ) {
        setPrivateSubConfirm({
          name: detail.subreddit,
          message: detail.message,
        });
      } else {
        toast.error(detail?.message || detail || "Failed to add subreddit");
      }
    } finally {
      setIsAdding(false);
    }
  };

  const handleConfirmPrivateSub = async () => {
    setPrivateSubConfirm(null);
    await handleAddSubreddit(true);
  };

  const handleDeleteSubreddit = async (id: number) => {
    try {
      const { data } = await subredditApi.delete(id);
      const displayName = `r/${data.subreddit}`;

      if (data.stories_deleted === 0) {
        toast.success(`Deleted ${displayName}`);
      } else {
        const storyWord = data.stories_deleted === 1 ? "story" : "stories";
        toast.success(
          `Deleted ${displayName} and ${data.stories_deleted} ${storyWord}`,
        );
      }

      refetchSubreddits();
      refetchStories();
      if (selectedSubreddit === data.subreddit) setSelectedSubreddit("all");
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const handleDeleteAllSubreddits = async () => {
    try {
      const { data } = await subredditApi.deleteAll();
      const storyWord = data.stories_deleted === 1 ? "story" : "stories";

      let message: string;
      if (data.count === 1 && data.subreddit_name) {
        if (data.stories_deleted === 0) {
          message = `Deleted r/${data.subreddit_name}`;
        } else {
          message = `Deleted r/${data.subreddit_name} and ${data.stories_deleted} ${storyWord}`;
        }
      } else {
        const subWord = data.count === 1 ? "subreddit" : "subreddits";
        if (data.stories_deleted === 0) {
          message = `Deleted ${data.count} ${subWord}`;
        } else {
          message = `Deleted ${data.count} ${subWord} and ${data.stories_deleted} ${storyWord}`;
        }
      }

      toast.success(message);
      refetchSubreddits();
      refetchStories();
      setSelectedSubreddit("all");
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const handleDeleteStory = async (story: Story) => {
    try {
      const { data } = await storyApi.delete(story.id);
      const updateWord = data.updates_deleted === 1 ? "update" : "updates";
      toast.success(
        `Deleted "${data.title}..." + ${data.updates_deleted} ${updateWord}`,
      );
      refetchStories();
      refreshNotifications();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const handleDeleteAllStories = async () => {
    try {
      const { data } = await storyApi.deleteAll();

      if (data.count === 0) {
        toast("No stories available to delete", {
          id: "delete-all",
          icon: <Info className="w-5 h-5 text-blue-500" />,
        });
      } else {
        const storyWord = data.count === 1 ? "story" : "stories";
        toast.success(`Deleted all ${data.count} ${storyWord}`, {
          id: "delete-all",
        });
      }

      refetchStories();
      refreshNotifications();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed", { id: "delete-all" });
    }
  };

  const handleLinkUpdates = async () => {
    try {
      toast.loading("Linking...", { id: "link" });
      const { data } = await storyApi.linkUpdates();

      if (data.reason === "no_subreddits") {
        toast("No active subreddits to link updates", {
          id: "link",
          icon: <Info className="w-5 h-5 text-blue-500" />,
        });
      } else if (data.reason === "no_updates") {
        toast("No update stories found to link", {
          id: "link",
          icon: <Info className="w-5 h-5 text-blue-500" />,
        });
      } else {
        const storyWord = data.linked_count === 1 ? "story" : "stories";
        toast.success(`Linked ${data.linked_count} update ${storyWord}`, {
          id: "link",
        });
      }

      await refreshNotifications();
      refetchStories();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed", { id: "link" });
    }
  };

  const activeSortLabel = SORT_OPTIONS.find((s) => s.value === sortBy)?.label;

  // Pagination calculations (top-level stories only; updates are nested)
  const topLevelStories = stories?.filter((s: Story) => !s.is_update) || [];
  const totalStories = topLevelStories.length;
  const totalPages = Math.ceil(totalStories / STORIES_PER_PAGE);
  const paginatedStories = topLevelStories.slice(
    (currentPage - 1) * STORIES_PER_PAGE,
    currentPage * STORIES_PER_PAGE,
  );
  const showingStart =
    totalStories === 0 ? 0 : (currentPage - 1) * STORIES_PER_PAGE + 1;
  const showingEnd = Math.min(currentPage * STORIES_PER_PAGE, totalStories);

  useEffect(() => {
    if (currentPage > totalPages && totalPages > 0) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  return (
    <div className="space-y-6">
      {/* Controls Row */}
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
            onClick={() => handleAddSubreddit()}
            disabled={isAdding}
            className="cursor-pointer btn-primary flex items-center gap-2"
          >
            {isAdding ? (
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            Add
          </button>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowFetchModal(true)}
            className="cursor-pointer btn-secondary flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Fetch
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

      {/* Filter & Sort Bar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative" ref={subredditDropdownRef}>
          <button
            onClick={() => setShowSubredditDropdown(!showSubredditDropdown)}
            className="cursor-pointer flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-gray-800 border border-border-light dark:border-border-dark rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
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
                  setSelectedSubreddit("all");
                  setShowSubredditDropdown(false);
                }}
                className={`cursor-pointer w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                  selectedSubreddit === "all"
                    ? "bg-primary/10 text-primary font-medium"
                    : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                }`}
              >
                <Filter className="w-4 h-4" />
                All Subreddits
              </button>
              {subreddits?.map((sub: any) => (
                <button
                  key={sub.id}
                  onClick={() => {
                    setSelectedSubreddit(sub.name);
                    setShowSubredditDropdown(false);
                  }}
                  className={`cursor-pointer w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                    selectedSubreddit === sub.name
                      ? "bg-primary/10 text-primary font-medium"
                      : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
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
            onClick={() => setShowSortDropdown(!showSortDropdown)}
            className="cursor-pointer flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-gray-800 border border-border-light dark:border-border-dark rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
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
                      setSortBy(option.value);
                      setShowSortDropdown(false);
                    }}
                    className={`cursor-pointer w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${sortBy === option.value ? "bg-primary/10 text-primary font-medium" : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"}`}
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
            onClick={() => setSelectedSubreddit("all")}
            className="cursor-pointer text-sm text-primary hover:underline"
          >
            Clear filter
          </button>
        )}

        <div className="flex-1 flex justify-end">
          <button
            onClick={() => setDeleteTarget({ type: "all_stories" })}
            className="cursor-pointer flex items-center gap-2 px-3 py-1.5 text-sm text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
            title="Delete all stories"
          >
            <Trash className="w-4 h-4" />
            Delete All Stories
          </button>
        </div>
      </div>

      {/* Stories */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      ) : paginatedStories.length > 0 ? (
        <div className="space-y-4">
          {paginatedStories.map((story: Story) => (
            <StoryCard
              key={story.id}
              story={story}
              onDelete={(s) => setDeleteTarget({ type: "story", story: s })}
            />
          ))}
        </div>
      ) : (
        <div className="card p-12 text-center">
          <BookOpen className="w-12 h-12 mx-auto mb-4 text-gray-300" />
          <h3 className="text-lg font-semibold text-gray-500">
            {selectedSubreddit !== "all"
              ? `No stories in r/${selectedSubreddit}`
              : "No stories yet"}
          </h3>
          <p className="text-sm text-gray-400 mt-1">
            {selectedSubreddit !== "all"
              ? "Try another subreddit or fetch new stories"
              : "Add a subreddit and click 'Fetch' to get started"}
          </p>
        </div>
      )}

      {/* Pagination */}
      {totalStories > 0 && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-4 border-t border-border-light dark:border-border-dark">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Showing{" "}
            <span className="font-medium text-gray-700 dark:text-gray-300">
              {showingStart}-{showingEnd}
            </span>{" "}
            of{" "}
            <span className="font-medium text-gray-700 dark:text-gray-300">
              {totalStories}
            </span>{" "}
            stories
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="cursor-pointer px-3 py-1.5 rounded-lg border border-border-light dark:border-border-dark text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            >
              Previous
            </button>
            <span className="text-sm font-medium px-2">
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="cursor-pointer px-3 py-1.5 rounded-lg border border-border-light dark:border-border-dark text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Modals */}
      {showFetchModal && subreddits && (
        <FetchModal
          subreddits={subreddits}
          onClose={() => setShowFetchModal(false)}
          onFetchComplete={() => {
            refetchStories();
            refreshNotifications();
          }}
        />
      )}

      {deleteTarget?.type === "single" && (
        <DeleteConfirmModal
          title="Remove Subreddit?"
          message={`Remove ${deleteTarget.name}?`}
          warning="All stories (including updates) will be permanently deleted."
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
          message={`Delete all ${subreddits?.length || 0} subreddits?`}
          warning="All subreddits and every story (including updates) will be deleted."
          onConfirm={() => {
            handleDeleteAllSubreddits();
            setDeleteTarget(null);
          }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
      {deleteTarget?.type === "story" && (
        <DeleteConfirmModal
          title="Delete Story?"
          message={`Delete "${deleteTarget.story.title}"?`}
          warning={
            deleteTarget.story.updates && deleteTarget.story.updates.length > 0
              ? `This will also delete ${deleteTarget.story.updates.length} linked update(s).`
              : "This action cannot be undone."
          }
          onConfirm={() => {
            handleDeleteStory(deleteTarget.story);
            setDeleteTarget(null);
          }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
      {deleteTarget?.type === "all_stories" && (
        <DeleteConfirmModal
          title="Delete All Stories?"
          message="Delete every story (including all updates)?"
          warning="Subreddits will NOT be deleted — only stories. This cannot be undone."
          onConfirm={() => {
            handleDeleteAllStories();
            setDeleteTarget(null);
          }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
      {privateSubConfirm && (
        <PrivateSubConfirmModal
          name={privateSubConfirm.name}
          message={privateSubConfirm.message}
          onConfirm={handleConfirmPrivateSub}
          onCancel={() => setPrivateSubConfirm(null)}
        />
      )}
    </div>
  );
}
