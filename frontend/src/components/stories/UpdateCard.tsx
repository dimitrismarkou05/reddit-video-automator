import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Clock, Film, Loader } from "lucide-react";
import { BranchConnector } from "./BranchConnector";
import { StoryMeta } from "./StoryMeta";
import { StoryActions } from "./StoryActions";
import { StoryBody } from "./StoryBody";
import { StatusBadge } from "@/components/common/StatusBadge";
import { GenerateVideoModal } from "@/components/GenerateVideoModal";
import { useVideoJobsStore } from "@/store/videoJobs";
import { stripUpdatePrefix } from "@/lib/formatters";
import toast from "react-hot-toast";
import type { Story } from "@/types";

interface UpdateCardProps {
  update: Story;
  index: number;
  totalUpdates: number;
  onDelete: (story: Story) => void;
  parentStoryId: number;
  canGenerate?: boolean;
  isDetectingFfmpeg?: boolean;
  parentStory?: Story | null;
}

export function UpdateCard({
  update,
  index,
  totalUpdates,
  onDelete,
  parentStoryId,
  canGenerate = true,
  isDetectingFfmpeg = false,
  parentStory = null,
}: UpdateCardProps) {
  const navigate = useNavigate();
  const [showGenerateModal, setShowGenerateModal] = useState(false);

  const { getModalVideoId, activeModalStoryId, activeModalVideoId } = useVideoJobsStore();

  const hasVideo = !!update.generated_video && update.generated_video.status === "done";
  const showNumberBadge = totalUpdates > 1;
  const updateNumber = index + 1;
  const cleanTitle = stripUpdatePrefix(update.title);

  // Check if this specific update is generating
  const updateGeneratingId = getModalVideoId(update.id, update.generated_video);
  const isThisUpdateGenerating = updateGeneratingId !== null;

  // Check if parent story is generating (meaning this update would be included)
  const parentGeneratingId = parentStory
    ? getModalVideoId(parentStory.id, parentStory.generated_video)
    : null;
  const isParentGenerating = parentGeneratingId !== null;

  const handleCardClick = (e: React.MouseEvent) => {
    // Don't navigate if clicking on action buttons
    const target = e.target as HTMLElement;
    if (target.closest("button") || target.closest("a")) {
      return;
    }
    navigate(`/stories/${parentStoryId}#update-${update.id}`);
  };

  const handleGenerate = useCallback(() => {
    if (isDetectingFfmpeg) return;
    if (!canGenerate) {
      toast.error("FFmpeg not installed. Please install FFmpeg in Settings to generate videos.");
      return;
    }

    // If parent is generating with include_updates, show parent's progress
    if (isParentGenerating && parentGeneratingId) {
      setShowGenerateModal(true);
      return;
    }

    // If this update is already generating, show its progress
    if (isThisUpdateGenerating && updateGeneratingId) {
      setShowGenerateModal(true);
      return;
    }

    // If has completed video, navigate to detail
    if (hasVideo) {
      navigate(`/stories/${parentStoryId}#update-${update.id}`);
      return;
    }

    // Otherwise open generation modal for this update
    setShowGenerateModal(true);
  }, [isThisUpdateGenerating, isParentGenerating, updateGeneratingId, parentGeneratingId, hasVideo, canGenerate, isDetectingFfmpeg, parentStoryId, update.id, navigate]);

  // Determine effective generating state for display
  const effectiveGenerating = isThisUpdateGenerating || isParentGenerating;
  const effectiveGeneratingId = updateGeneratingId || parentGeneratingId;

  return (
    <div className="flex">
      <BranchConnector index={index} total={totalUpdates} />
      <div className="flex-1 pb-3">
        <div
          onClick={handleCardClick}
          className="card p-4 hover:shadow-md  cursor-pointer"
        >
          <div className="flex items-start gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <StatusBadge label="Update" icon={Clock} variant="warning" />
                {showNumberBadge && (
                  <StatusBadge label={`#${updateNumber}`} variant="neutral" />
                )}
                {hasVideo && (
                  <StatusBadge
                    label="Video Ready"
                    icon={Film}
                    variant="success"
                  />
                )}
                {effectiveGenerating && (
                  <StatusBadge
                    label={isParentGenerating ? "Included in parent" : "Generating..."}
                    variant="warning"
                  />
                )}
              </div>
              <h3 className="font-semibold text-base mb-1">{cleanTitle}</h3>
              <StoryMeta story={update} />
              <StoryBody body={update.body} />
            </div>
            <div onClick={(e) => e.stopPropagation()}>
              <StoryActions
                hasVideo={hasVideo}
                permalink={update.permalink}
                onGenerate={handleGenerate}
                onDelete={() => onDelete(update)}
                canGenerate={canGenerate}
                isDetectingFfmpeg={isDetectingFfmpeg}
                isGenerating={effectiveGenerating}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Modal: if parent is generating, show parent story modal. Otherwise show update modal */}
      {showGenerateModal && (
        isParentGenerating && parentStory ? (
          <GenerateVideoModal
            story={parentStory}
            onClose={() => setShowGenerateModal(false)}
            existingVideoId={parentGeneratingId}
            isUpdate={false}
          />
        ) : (
          <GenerateVideoModal
            story={update}
            onClose={() => setShowGenerateModal(false)}
            existingVideoId={updateGeneratingId}
            isUpdate={true}
            parentStory={parentStory}
          />
        )
      )}
    </div>
  );
}
