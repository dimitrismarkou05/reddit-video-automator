import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, RefreshCw, Link2, BookOpen, Info } from "lucide-react";
import { storyApi, subredditApi } from "@/services/api";
import { useNotificationStore } from "@/store";
import { notificationApi } from "@/services/api";
import { FetchModal } from "@/components/FetchModal";
import { SubredditList } from "@/components/stories/SubredditList";
import { StoryCard } from "@/components/stories/StoryCard";
import { StoryFilters } from "@/components/stories/StoryFilters";
import { StoryPagination } from "@/components/stories/StoryPagination";
import { DeleteConfirmModal } from "@/components/modals/DeleteConfirmModal";
import { PrivateSubConfirmModal } from "@/components/modals/PrivateSubConfirmModal";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadingSpinner } from "@/components/common/LoadingSpinner";
import { useDeleteTarget } from "@/hooks/useDeleteTarget";
import { useFfmpegStatus } from "@/hooks/useFfmpegStatus";
import type { Story } from "@/types";
import type { SortOption } from "@/config/sortOptions";
import toast from "react-hot-toast";

const STORIES_PER_PAGE = 10;

export function StoriesPage() {
  const [newSubreddit, setNewSubreddit] = useState("");
  const [isAdding, setIsAdding] = useState(false);
  const { setNotifications } = useNotificationStore();

  const [selectedSubreddit, setSelectedSubreddit] = useState<string>("all");
  const [sortBy, setSortBy] = useState<SortOption>("date_desc");
  const [showSortDropdown, setShowSortDropdown] = useState(false);
  const [showSubredditDropdown, setShowSubredditDropdown] = useState(false);
  const [showFetchModal, setShowFetchModal] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");

  const [privateSubConfirm, setPrivateSubConfirm] = useState<{
    name: string;
    message: string;
  } | null>(null);

  const {
    deleteTarget,
    clearTarget,
    setSingle,
    setAll,
    setStory,
    setAllStories,
  } = useDeleteTarget();

  const { status: ffmpegStatus, isLoading: ffmpegLoading } = useFfmpegStatus();
  const canGenerate = ffmpegStatus?.can_generate_videos ?? false;
  const isDetectingFfmpeg = ffmpegLoading && !ffmpegStatus;

  const scrollRef = useRef<HTMLDivElement>(null);

  const {
    data: storiesData,
    isLoading,
    refetch: refetchStories,
  } = useQuery({
    queryKey: ["stories", selectedSubreddit, sortBy, currentPage, searchQuery],
    queryFn: async () => {
      const params: Record<string, any> = {
        page: currentPage,
        limit: STORIES_PER_PAGE,
        sort_by: sortBy,
      };
      if (selectedSubreddit !== "all") params.subreddit = selectedSubreddit;
      if (searchQuery.trim()) params.search = searchQuery.trim();
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

  // Reset to page 1 when filters or search change
  useEffect(() => {
    setCurrentPage(1);
  }, [selectedSubreddit, sortBy, searchQuery]);

  // Scroll to top on page change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = 0;
    }
  }, [currentPage]);

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
        message =
          data.stories_deleted === 0
            ? `Deleted r/${data.subreddit_name}`
            : `Deleted r/${data.subreddit_name} and ${data.stories_deleted} ${storyWord}`;
      } else {
        const subWord = data.count === 1 ? "subreddit" : "subreddits";
        message =
          data.stories_deleted === 0
            ? `Deleted ${data.count} ${subWord}`
            : `Deleted ${data.count} ${subWord} and ${data.stories_deleted} ${storyWord}`;
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
        `Deleted "${data.title}" and ${data.updates_deleted} ${updateWord}`,
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

  // Extract from paginated response
  const paginatedStories = storiesData?.items || [];
  const totalStories = storiesData?.total || 0;
  const totalPages = storiesData?.pages || 1;
  const showingStart =
    totalStories === 0 ? 0 : (currentPage - 1) * STORIES_PER_PAGE + 1;
  const showingEnd = Math.min(currentPage * STORIES_PER_PAGE, totalStories);

  return (
    <div className="flex flex-col h-full gap-6">
      {/* ═══ Pinned Top: Controls, Subreddits, Filters ═══ */}
      <div className="shrink-0 space-y-6">
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
            onDelete={(id, name) => setSingle(id, name)}
            onDeleteAll={() => setAll()}
          />
        )}

        {/* Filter & Sort Bar */}
        <StoryFilters
          subreddits={subreddits || []}
          selectedSubreddit={selectedSubreddit}
          onSelectSubreddit={setSelectedSubreddit}
          sortBy={sortBy}
          onSelectSort={setSortBy}
          showSubredditDropdown={showSubredditDropdown}
          onToggleSubredditDropdown={() => setShowSubredditDropdown((v) => !v)}
          showSortDropdown={showSortDropdown}
          onToggleSortDropdown={() => setShowSortDropdown((v) => !v)}
          onDeleteAllStories={() => setAllStories()}
          setShowSubredditDropdown={setShowSubredditDropdown}
          setShowSortDropdown={setShowSortDropdown}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
        />
      </div>

      {/* ═══ Scrollable Middle: Stories List ═══ */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto min-h-0 pr-1">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <LoadingSpinner size="md" />
          </div>
        ) : paginatedStories.length > 0 ? (
          <div className="space-y-4 pb-2">
            {paginatedStories.map((story: Story) => (
              <StoryCard
                key={story.id}
                story={story}
                onDelete={(s) => setStory(s)}
                canGenerate={canGenerate}
                isDetectingFfmpeg={isDetectingFfmpeg}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={BookOpen}
            title={
              selectedSubreddit !== "all"
                ? `No stories in r/${selectedSubreddit}`
                : searchQuery
                  ? `No stories matching "${searchQuery}"`
                  : "No stories yet"
            }
            subtitle={
              selectedSubreddit !== "all"
                ? "Try another subreddit or fetch new stories"
                : searchQuery
                  ? "Try a different search term"
                  : "Add a subreddit and click 'Fetch' to get started"
            }
          />
        )}
      </div>

      {/* ═══ Pinned Bottom: Pagination ═══ */}
      <div className="shrink-0">
        <StoryPagination
          currentPage={currentPage}
          totalPages={totalPages}
          showingStart={showingStart}
          showingEnd={showingEnd}
          totalStories={totalStories}
          onPageChange={setCurrentPage}
        />
      </div>

      {/* ═══ Modals ═══ */}
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
            clearTarget();
          }}
          onCancel={clearTarget}
        />
      )}
      {deleteTarget?.type === "all" && (
        <DeleteConfirmModal
          title="Delete All Subreddits?"
          message={`Delete all ${subreddits?.length || 0} subreddits?`}
          warning="All subreddits and every story (including updates) will be deleted."
          onConfirm={() => {
            handleDeleteAllSubreddits();
            clearTarget();
          }}
          onCancel={clearTarget}
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
            clearTarget();
          }}
          onCancel={clearTarget}
        />
      )}
      {deleteTarget?.type === "all_stories" && (
        <DeleteConfirmModal
          title="Delete All Stories?"
          message="Delete every story (including all updates)?"
          warning="Subreddits will NOT be deleted — only stories. This cannot be undone."
          onConfirm={() => {
            handleDeleteAllStories();
            clearTarget();
          }}
          onCancel={clearTarget}
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
