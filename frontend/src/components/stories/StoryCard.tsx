import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ChevronRight, GitBranch, Clock } from "lucide-react";
import { StoryMeta } from "./StoryMeta";
import { StoryActions } from "./StoryActions";
import { StoryBody } from "./StoryBody";
import { UpdateCard } from "./UpdateCard";
import { StatusBadge } from "@/components/common/StatusBadge";
import { GenerateVideoModal } from "@/components/GenerateVideoModal";
import { useVideoJobsStore } from "@/store/videoJobs";
import toast from "react-hot-toast";
import type { Story } from "@/types";

// FIX 4: Terminal statuses that mean video generation is complete/failed/cancelled
const TERMINAL_VIDEO_STATUSES = ["done", "failed", "cancelled"];

interface StoryCardProps {
  story: Story;
  onDelete: (story: Story) => void;
  canGenerate?: boolean;
  isDetectingFfmpeg?: boolean;
}

export function StoryCard({ story, onDelete, canGenerate = true, isDetectingFfmpeg = false }: StoryCardProps) {
  const navigate = useNavigate();
  const [showUpdates, setShowUpdates] = useState(false);
  const [showGenerateModal, setShowGenerateModal] = useState(false);

  const { getModalVideoId, activeModalVideoId, activeModalStoryId } = useVideoJobsStore();

  const hasUpdates = story.updates && story.updates.length > 0;
  // FIX 4: Only consider video "done" when status is "done", not when just existing
  const hasCompletedVideo = !!story.generated_video && story.generated_video.status === "done";
  const hasActiveVideo = !!story.generated_video && !TERMINAL_VIDEO_STATUSES.includes(story.generated_video.status);
  const updateCount = story.updates?.length || 0;

  // Check if this story or any of its updates are currently generating
  const generatingVideoId = getModalVideoId(story.id, story.generated_video);
  const isThisStoryGenerating = generatingVideoId !== null;

  const handleCardClick = (e: React.MouseEvent) => {
    // Don't navigate if clicking on action buttons or the updates toggle
    const target = e.target as HTMLElement;
    if (
      target.closest("button") ||
      target.closest("a") ||
      target.closest("[data-no-nav]")
    ) {
      return;
    }
    navigate(`/stories/${story.id}`);
  };

  const handleGenerate = useCallback(() => {
    if (isDetectingFfmpeg) return;
    if (!canGenerate) {
      toast.error("FFmpeg not installed. Please install FFmpeg in Settings to generate videos.");
      return;
    }

    // If already generating, show the existing progress modal
    if (isThisStoryGenerating && generatingVideoId) {
      // Modal is already showing for this story's generation
      if (activeModalStoryId === story.id && showGenerateModal) {
        return; // Already open
      }
      setShowGenerateModal(true);
      return;
    }

    // If has completed video, navigate to detail
    if (hasCompletedVideo) {
      navigate(`/stories/${story.id}`);
      return;
    }

    // Otherwise open generation modal
    setShowGenerateModal(true);
  }, [isThisStoryGenerating, generatingVideoId, hasCompletedVideo, canGenerate, isDetectingFfmpeg, story.id, activeModalStoryId, showGenerateModal, navigate]);

  return (
    <div className="space-y-0">
      <div
        onClick={handleCardClick}
        className="card p-4 hover:shadow-md  cursor-pointer"
      >
        <div className="flex items-start gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <StatusBadge label={`r/${story.subreddit}`} variant="primary" />
              {story.is_update && (
                <StatusBadge label="Update" variant="warning" />
              )}
              {hasCompletedVideo && (
                <StatusBadge
                  label="Video Ready"
                  icon={Clock}
                  variant="success"
                />
              )}
              {hasActiveVideo && (
                <StatusBadge
                  label={story.generated_video?.status === "paused" ? "Paused" : "Generating..."}
                  variant={story.generated_video?.status === "paused" ? "neutral" : "warning"}
                />
              )}
              {isThisStoryGenerating && !hasActiveVideo && (
                <StatusBadge
                  label="Generating..."
                  variant="warning"
                />
              )}
              {hasUpdates && (
                <>
                  <StatusBadge
                    label={`${updateCount} update${updateCount !== 1 ? "s" : ""}`}
                    icon={Clock}
                    variant="warning"
                  />
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowUpdates(!showUpdates);
                    }}
                    data-no-nav
                    className="cursor-pointer -ml-0.5 p-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700  shrink-0 inline-flex items-center gap-0.5"
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
                    <GitBranch className="w-3 h-3 text-primary mr-0.75" />
                  </button>
                </>
              )}
            </div>
            <h3 className="font-semibold text-base mb-1">{story.title}</h3>
            <StoryMeta story={story} />
            <StoryBody body={story.body} />
          </div>
          <div onClick={(e) => e.stopPropagation()} data-no-nav>
            <StoryActions
              hasVideo={hasCompletedVideo}
              permalink={story.permalink}
              onGenerate={handleGenerate}
              onDelete={() => onDelete(story)}
              canGenerate={canGenerate}
              isDetectingFfmpeg={isDetectingFfmpeg}
              isGenerating={isThisStoryGenerating || hasActiveVideo}
            />
          </div>
        </div>
      </div>

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
                parentStoryId={story.id}
                canGenerate={canGenerate}
                isDetectingFfmpeg={isDetectingFfmpeg}
                parentStory={story}
              />
            ))}
          </div>
        </div>
      )}

      {showGenerateModal && (
        <GenerateVideoModal
          story={story}
          onClose={() => setShowGenerateModal(false)}
          existingVideoId={generatingVideoId}
        />
      )}
    </div>
  );
}
