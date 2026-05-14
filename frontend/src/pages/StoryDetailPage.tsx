import { useEffect, useRef, useState } from "react";
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
} from "lucide-react";
import { storyApi } from "@/services/api";
import { StatusBadge } from "@/components/common/StatusBadge";
import { LoadingSpinner } from "@/components/common/LoadingSpinner";
import { EmptyState } from "@/components/common/EmptyState";
import { GenerateVideoModal } from "@/components/GenerateVideoModal";
import { DeleteConfirmModal } from "@/components/modals/DeleteConfirmModal";
import { formatUtcRelative, stripUpdatePrefix } from "@/lib/formatters";
import type { Story } from "@/types";
import toast from "react-hot-toast";

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

function UpdateSection({
  update,
  index,
  isLast,
}: {
  update: Story;
  index: number;
  isLast: boolean;
}) {
  const updateNumber = index + 1;
  const cleanTitle = stripUpdatePrefix(update.title);
  const hasVideo = !!update.generated_video;
  const sectionRef = useRef<HTMLDivElement>(null);

  return (
    <div ref={sectionRef} id={`update-${update.id}`} className="scroll-mt-6">
      {/* Update header badge */}
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

      {/* Update title */}
      {cleanTitle && (
        <h3 className="text-lg font-semibold mb-2 text-gray-900 dark:text-gray-100">
          {cleanTitle}
        </h3>
      )}

      {/* Update meta */}
      <StoryMetaLine story={update} />

      {/* Update body */}
      {update.body && (
        <div className="mt-3 text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
          {update.body}
        </div>
      )}

      {/* Update actions */}
      <UpdateActions update={update} />

      {!isLast && (
        <div className="my-6 border-b border-border-light dark:border-border-dark" />
      )}
    </div>
  );
}

function UpdateActions({ update }: { update: Story }) {
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const handleDelete = async () => {
    try {
      const { data } = await storyApi.delete(update.id);
      const updateWord = data.updates_deleted === 1 ? "update" : "updates";
      toast.success(
        `Deleted "${data.title}" and ${data.updates_deleted} ${updateWord}`,
      );
      queryClient.invalidateQueries({ queryKey: ["stories"] });
      navigate("/stories");
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to delete");
    }
  };

  return (
    <>
      <div className="flex items-center gap-2 mt-4">
        <button
          onClick={() => setShowGenerateModal(true)}
          disabled={!!update.generated_video}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            update.generated_video
              ? "bg-green-100 dark:bg-green-900/30 text-green-600 cursor-default"
              : "bg-primary/10 text-primary hover:bg-primary/20"
          }`}
        >
          <Film className="w-4 h-4" />
          {update.generated_video ? "Video Ready" : "Generate Video"}
        </button>
        <a
          href={update.permalink}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
        >
          <ExternalLink className="w-4 h-4" />
          View on Reddit
        </a>
        <button
          onClick={() => setShowDeleteModal(true)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium bg-red-50 dark:bg-red-900/20 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
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

export function StoryDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

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

  // Handle anchor scrolling after content loads
  useEffect(() => {
    if (story && location.hash) {
      const targetId = location.hash.replace("#", "");
      const el = document.getElementById(targetId);
      if (el) {
        setTimeout(() => {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 100);
      }
    }
  }, [story, location.hash]);

  const handleDelete = async () => {
    try {
      const { data } = await storyApi.delete(Number(id));
      const updateWord = data.updates_deleted === 1 ? "update" : "updates";
      toast.success(
        `Deleted "${data.title}" and ${data.updates_deleted} ${updateWord}`,
      );
      navigate("/stories");
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to delete");
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background-light dark:bg-background-dark">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error || !story) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background-light dark:bg-background-dark p-4">
        <EmptyState
          icon={MessageCircle}
          title="Story not found"
          subtitle="The story you're looking for doesn't exist or has been deleted."
        />
      </div>
    );
  }

  const hasVideo = !!story.generated_video;
  const updateCount = story.updates?.length || 0;
  const hasUpdates = updateCount > 0;

  return (
    <div className="min-h-screen bg-background-light dark:bg-background-dark">
      {/* Top Navigation Bar */}
      <header className="sticky top-0 z-500 bg-surface-light/80 dark:bg-surface-dark/80 backdrop-blur-md border-b border-border-light dark:border-border-dark">
        <div className="max-w-3xl mx-auto px-4 h-14 flex items-center gap-3">
          <button
            onClick={() => navigate("/stories")}
            className="cursor-pointer p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-2">
            <StatusBadge label={`r/${story.subreddit}`} variant="primary" />
            {story.is_update && (
              <StatusBadge label="Update" variant="warning" />
            )}
          </div>
          <div className="flex-1" />
          {hasUpdates && (
            <span className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
              <GitBranch className="w-3 h-3" />
              {updateCount} update{updateCount !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-4 py-6" ref={contentRef}>
        {/* Original Story */}
        <article className="card p-6">
          {/* Title */}
          <h1 className="text-2xl font-bold mb-3 text-gray-900 dark:text-gray-100 leading-tight">
            {story.title}
          </h1>

          {/* Meta */}
          <StoryMetaLine story={story} />

          {/* Body */}
          {story.body && (
            <div className="mt-4 text-gray-800 dark:text-gray-200 leading-relaxed whitespace-pre-wrap text-[15px]">
              {story.body}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 mt-6 pt-4 border-t border-border-light dark:border-border-dark">
            <button
              onClick={() => setShowGenerateModal(true)}
              disabled={hasVideo}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                hasVideo
                  ? "bg-green-100 dark:bg-green-900/30 text-green-600 cursor-default"
                  : "bg-primary/10 text-primary hover:bg-primary/20"
              }`}
            >
              <Film className="w-4 h-4" />
              {hasVideo ? "Video Ready" : "Generate Video"}
            </button>
            <a
              href={story.permalink}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
              View on Reddit
            </a>
            <button
              onClick={() => setShowDeleteModal(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-red-50 dark:bg-red-900/20 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Delete
            </button>
          </div>
        </article>

        {/* Updates Section */}
        {hasUpdates && (
          <div className="mt-6">
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
                />
              ))}
            </div>
          </div>
        )}
      </main>

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
