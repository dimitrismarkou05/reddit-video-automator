import { useEffect, useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowUp,
  MessageCircle,
  Calendar,
  ExternalLink,
  Film,
  Trash2,
  Clock,
  GitBranch,
  ChevronUp,
  Bookmark,
  Share2,
} from "lucide-react";
import { storyApi } from "@/services/api";
import { StatusBadge } from "@/components/common/StatusBadge";
import { LoadingSpinner } from "@/components/common/LoadingSpinner";
import { EmptyState } from "@/components/common/EmptyState";
import { GenerateVideoModal } from "@/components/GenerateVideoModal";
import { DeleteConfirmModal } from "@/components/modals/DeleteConfirmModal";
import { formatUtcRelative, stripUpdatePrefix } from "@/lib/formatters";
import { useFfmpegStatus } from "@/hooks/useFfmpegStatus";
import type { Story } from "@/types";
import toast from "react-hot-toast";
import { renderMarkdownLinks } from "@/lib/renderMarkdownLinks";

/* ─── Meta line ─── */
function StoryMetaLine({ story }: { story: Story }) {
  return (
    <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400 flex-wrap">
      <span className="flex items-center gap-1">
        <ArrowUp className="w-3.5 h-3.5" />
        {story.score.toLocaleString()}
      </span>
      <span className="flex items-center gap-1">
        <MessageCircle className="w-3.5 h-3.5" />
        u/{story.author}
      </span>
      <span className="flex items-center gap-1">
        <Calendar className="w-3.5 h-3.5" />
        {formatUtcRelative(story.created_utc)}
      </span>
    </div>
  );
}

/* ─── Sidebar: jump links ─── */
function UpdateSidebar({
  updates,
  activeId,
}: {
  updates: Story[];
  activeId: string | null;
}) {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="card p-4 sticky top-12">
      <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
        <GitBranch className="w-3.5 h-3.5" />
        Jump to Update
      </h3>
      <nav className="space-y-1">
        {updates.map((update, idx) => {
          const isActive = activeId === `update-${update.id}`;
          const clean = stripUpdatePrefix(update.title);
          const preview = clean.length > 40 ? clean.slice(0, 37) + "…" : clean;
          return (
            <button
              key={update.id}
              onClick={() => {
                navigate(`${location.pathname}#update-${update.id}`, {
                  replace: true,
                });
                document
                  .getElementById(`update-${update.id}`)
                  ?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
              className={`cursor-pointer w-full text-left px-3 py-2 rounded-lg text-sm  ${
                isActive
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5"
              }`}
            >
              <span className="text-xs text-gray-400 mr-1.5">#{idx + 1}</span>
              {preview || `Update ${idx + 1}`}
            </button>
          );
        })}
      </nav>
    </div>
  );
}

/* ─── Sidebar: story info ─── */
function StoryInfoSidebar({ story }: { story: Story }) {
  return (
    <div className="card p-4">
      <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
        <Bookmark className="w-3.5 h-3.5" />
        Story Info
      </h3>
      <div className="space-y-3 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-500">Subreddit</span>
          <span className="font-medium">r/{story.subreddit}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Author</span>
          <span className="font-medium">u/{story.author}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Score</span>
          <span className="font-medium">{story.score.toLocaleString()}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Date</span>
          <span className="font-medium">
            {formatUtcRelative(story.created_utc)}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Status</span>
          <StatusBadge label={story.status} variant="neutral" />
        </div>
        {story.update_reason && (
          <div className="pt-2 border-t border-border-light dark:border-border-dark">
            <span className="text-gray-500 text-xs block mb-1">Note</span>
            <span className="text-xs text-gray-600 dark:text-gray-400">
              {story.update_reason}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Update section ─── */
function UpdateSection({
  update,
  index,
  isLast,
  canGenerate,
}: {
  update: Story;
  index: number;
  isLast: boolean;
  canGenerate: boolean;
}) {
  const updateNumber = index + 1;
  const cleanTitle = stripUpdatePrefix(update.title);
  const hasVideo = !!update.generated_video;

  return (
    <div id={`update-${update.id}`} className="scroll-mt-20">
      <div className="flex items-center gap-2 mb-3">
        <div className="flex items-center gap-2 px-3 py-1.5 bg-yellow-100 dark:bg-yellow-900/30 border border-yellow-200 dark:border-yellow-800 rounded-full">
          <GitBranch className="w-3.5 h-3.5 text-yellow-700 dark:text-yellow-400" />
          <span className="text-sm font-semibold text-yellow-800 dark:text-yellow-300">
            Update {updateNumber}
          </span>
        </div>
        {hasVideo && (
          <StatusBadge label="Video Ready" icon={Clock} variant="success" />
        )}
      </div>

      {cleanTitle && (
        <h3 className="text-lg font-semibold mb-2 text-gray-900 dark:text-gray-100">
          {cleanTitle}
        </h3>
      )}

      <StoryMetaLine story={update} />

      {update.body && (
        <div className="mt-3 text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
          {renderMarkdownLinks(update.body)}
        </div>
      )}

      <UpdateActions update={update} canGenerate={canGenerate} />

      {!isLast && (
        <div className="my-8 border-b border-border-light dark:border-border-dark" />
      )}
    </div>
  );
}

/* ─── Actions for an individual update ─── */
function UpdateActions({ update, canGenerate }: { update: Story; canGenerate: boolean }) {
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const handleDelete = async () => {
    try {
      const { data } = await storyApi.delete(update.id);
      const word = data.updates_deleted === 1 ? "update" : "updates";
      toast.success(
        `Deleted "${data.title}" and ${data.updates_deleted} ${word}`,
      );
      queryClient.invalidateQueries({ queryKey: ["stories"] });
      navigate("/stories");
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to delete");
    }
  };

  const handleGenerateClick = () => {
    if (!canGenerate) {
      toast.error("FFmpeg not installed. Please install FFmpeg in Settings to generate videos.");
      return;
    }
    setShowGenerateModal(true);
  };

  return (
    <>
      <div className="flex items-center gap-2 mt-4">
        <button
          onClick={handleGenerateClick}
          disabled={!!update.generated_video}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium  ${
            update.generated_video
              ? "bg-green-100 dark:bg-green-900/30 text-green-600 cursor-default"
              : canGenerate
                ? "bg-primary/10 text-primary hover:bg-primary/20 cursor-pointer"
                : "bg-gray-100 dark:bg-surface-dark dark:border dark:border-border-dark text-gray-400 cursor-not-allowed"
          }`}
        >
          <Film className="w-4 h-4" />
          {update.generated_video ? "Video Ready" : "Generate Video"}
        </button>
        <a
          href={update.permalink}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium bg-gray-100 dark:bg-surface-dark dark:border dark:border-border-dark text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-white/5 "
        >
          <ExternalLink className="w-4 h-4" />
          View on Reddit
        </a>
        <button
          onClick={() => setShowDeleteModal(true)}
          className="cursor-pointer flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium bg-red-50 dark:bg-red-900/20 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/30 "
        >
          <Trash2 className="w-4 h-4" />
          Delete
        </button>
      </div>

      {showGenerateModal && (
        <GenerateVideoModal
          story={update}
          onClose={() => setShowGenerateModal(false)}
        />
      )}
      {showDeleteModal && (
        <DeleteConfirmModal
          title="Delete Update?"
          message={`Delete "${update.title}"?`}
          warning="This action cannot be undone."
          onConfirm={() => {
            handleDelete();
            setShowDeleteModal(false);
          }}
          onCancel={() => setShowDeleteModal(false)}
        />
      )}
    </>
  );
}

/* ─── Main page ─── */
export function StoryDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [activeHash, setActiveHash] = useState<string | null>(
    location.hash ? location.hash.replace("#", "") : null,
  );
  const isElectron = !!window.electronAPI;

  const { status: ffmpegStatus } = useFfmpegStatus();
  const canGenerate = ffmpegStatus?.can_generate_videos ?? false;

  const {
    data: story,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["story", id],
    queryFn: async () => {
      const { data } = await storyApi.get(Number(id));
      return data;
    },
  });

  /* scroll to anchor on load */
  useEffect(() => {
    if (story && location.hash) {
      const targetId = location.hash.replace("#", "");
      setActiveHash(targetId);
      setTimeout(() => {
        document
          .getElementById(targetId)
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 120);
    }
  }, [story, location.hash]);

  /* track active section while scrolling */
  useEffect(() => {
    if (!story?.updates?.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setActiveHash(entry.target.id);
          }
        });
      },
      { rootMargin: "-120px 0px -60% 0px", threshold: 0 },
    );
    story.updates.forEach((u: Story) => {
      const el = document.getElementById(`update-${u.id}`);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [story]);

  const handleDelete = async () => {
    try {
      const { data } = await storyApi.delete(Number(id));
      const word = data.updates_deleted === 1 ? "update" : "updates";
      toast.success(
        `Deleted "${data.title}" and ${data.updates_deleted} ${word}`,
      );
      navigate("/stories");
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to delete");
    }
  };

  const handleGenerateClick = () => {
    if (!canGenerate) {
      toast.error("FFmpeg not installed. Please install FFmpeg in Settings to generate videos.");
      return;
    }
    setShowGenerateModal(true);
  };

  if (isLoading) {
    return (
      <div
        className={`${isElectron ? "h-full" : "min-h-screen"} flex items-center justify-center bg-background-light dark:bg-background-dark`}
      >
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error || !story) {
    return (
      <div
        className={`${isElectron ? "h-full" : "min-h-screen"} flex items-center justify-center bg-background-light dark:bg-background-dark p-4`}
      >
        <EmptyState
          icon={MessageCircle}
          title="Story not found"
          subtitle="The story you are looking for does not exist or has been deleted."
        />
      </div>
    );
  }

  const hasVideo = !!story.generated_video;
  const updateCount = story.updates?.length || 0;
  const hasUpdates = updateCount > 0;

  return (
    <div
      className={`${isElectron ? "h-full" : "min-h-screen"} bg-background-light dark:bg-background-dark`}
    >
      {/* Full-width sticky nav */}
      <header className="sticky -top-6 z-50 -mx-6 -mt-6 bg-surface-light/95 dark:bg-surface-dark/95 backdrop-blur-md border-b border-border-light dark:border-border-dark">
        <div className="max-w-6xl mx-auto h-14 px-4 sm:px-6 flex items-center gap-3">
          <button
            onClick={() => navigate("/stories")}
            className="cursor-pointer p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-white/5  shrink-0"
            title="Back to stories"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>

          <div className="w-px h-6 bg-border-light dark:bg-border-dark shrink-0" />

          <div className="flex items-center gap-2 min-w-0">
            <StatusBadge label={`r/${story.subreddit}`} variant="primary" />
            {story.is_update && (
              <StatusBadge label="Update" variant="warning" />
            )}
          </div>

          <span className="hidden sm:block text-sm text-gray-500 dark:text-gray-400 truncate min-w-0">
            {story.title}
          </span>

          <div className="flex-1" />

          <div className="flex items-center gap-1 shrink-0">
            {hasUpdates && (
              <span className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-gray-100 dark:bg-surface-dark dark:border dark:border-border-dark text-xs text-gray-600 dark:text-gray-400">
                <GitBranch className="w-3 h-3" />
                {updateCount} update{updateCount !== 1 ? "s" : ""}
              </span>
            )}
            <button
              onClick={() => {
                navigator.clipboard.writeText(story.permalink);
                toast.success("Reddit link copied to clipboard");
              }}
              className="cursor-pointer p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-white/5 "
              title="Copy Reddit link"
            >
              <Share2 className="w-4 h-4 text-gray-500" />
            </button>
            <button
              onClick={() => setShowDeleteModal(true)}
              className="cursor-pointer p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 "
              title="Delete story"
            >
              <Trash2 className="w-4 h-4 text-red-500" />
            </button>
          </div>
        </div>
      </header>

      {/* Content grid */}
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
          {/* Main column */}
          <div className="space-y-6 min-w-0">
            {/* Original story */}
            <article className="card p-6">
              <h1 className="text-xl sm:text-2xl font-bold mb-3 text-gray-900 dark:text-gray-100 leading-snug">
                {story.title}
              </h1>

              <StoryMetaLine story={story} />

              {story.body && (
                <div className="mt-4 text-gray-800 dark:text-gray-200 leading-relaxed whitespace-pre-wrap text-[15px]">
                  {renderMarkdownLinks(story.body)}
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2 mt-6 pt-4 border-t border-border-light dark:border-border-dark">
                <button
                  onClick={handleGenerateClick}
                  disabled={hasVideo}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium  ${
                    hasVideo
                      ? "bg-green-100 dark:bg-green-900/30 text-green-600 cursor-default"
                      : canGenerate
                        ? "bg-primary/10 text-primary hover:bg-primary/20 cursor-pointer"
                        : "bg-gray-100 dark:bg-surface-dark dark:border dark:border-border-dark text-gray-400 cursor-not-allowed"
                  }`}
                >
                  <Film className="w-4 h-4" />
                  {hasVideo ? "Video Ready" : "Generate Video"}
                </button>
                <a
                  href={story.permalink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-gray-100 dark:bg-surface-dark dark:border dark:border-border-dark text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-white/5 "
                >
                  <ExternalLink className="w-4 h-4" />
                  View on Reddit
                </a>
              </div>
            </article>

            {/* Updates */}
            {hasUpdates && (
              <div>
                <div className="flex items-center gap-2 mb-4 px-1">
                  <ChevronUp className="w-4 h-4 text-primary" />
                  <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Updates
                  </h2>
                  <div className="flex-1 h-px bg-border-light dark:bg-border-dark ml-2" />
                </div>

                <div className="card p-6 space-y-2">
                  {story.updates?.map((update: Story, index: number) => (
                    <UpdateSection
                      key={update.id}
                      update={update}
                      index={index}
                      isLast={index === updateCount - 1}
                      canGenerate={canGenerate}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right sidebar */}
          <aside className="hidden lg:block space-y-4">
            <StoryInfoSidebar story={story} />
            {hasUpdates && (
              <UpdateSidebar updates={story.updates} activeId={activeHash} />
            )}
          </aside>
        </div>
      </div>

      {/* Modals */}
      {showGenerateModal && (
        <GenerateVideoModal
          story={story}
          onClose={() => setShowGenerateModal(false)}
        />
      )}
      {showDeleteModal && (
        <DeleteConfirmModal
          title="Delete Story?"
          message={`Delete "${story.title}"?`}
          warning={
            hasUpdates
              ? `This will also delete ${updateCount} linked update(s).`
              : "This action cannot be undone."
          }
          onConfirm={() => {
            handleDelete();
            setShowDeleteModal(false);
          }}
          onCancel={() => setShowDeleteModal(false)}
        />
      )}
    </div>
  );
}
