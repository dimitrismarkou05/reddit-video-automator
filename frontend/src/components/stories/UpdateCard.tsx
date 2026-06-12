import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Clock } from "lucide-react";
import { BranchConnector } from "./BranchConnector";
import { StoryMeta } from "./StoryMeta";
import { StoryActions } from "./StoryActions";
import { StoryBody } from "./StoryBody";
import { StatusBadge } from "@/components/common/StatusBadge";
import { StoryVideoProgress } from "@/components/videos/StoryVideoProgress";
import { GenerateVideoModal } from "@/components/GenerateVideoModal";
import { UploadModal } from "@/components/UploadModal";
import { useStoryGenerationState } from "@/hooks/useStoryGenerationState";
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
  const [showUploadModal, setShowUploadModal] = useState(false);

  const hasVideo = !!update.generated_video && update.generated_video.status === "done";
  const showNumberBadge = totalUpdates > 1;
  const updateNumber = index + 1;
  const cleanTitle = stripUpdatePrefix(update.title);

  const { isGenerating: isThisUpdateGenerating, activeVideoId: updateGeneratingId } =
    useStoryGenerationState(update.id, update.generated_video);
  const { isGenerating: isParentGenerating, activeVideoId: parentGeneratingId } =
    useStoryGenerationState(parentStory?.id ?? 0, parentStory?.generated_video);

  const handleCardClick = (e: React.MouseEvent) => {
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

    if (isParentGenerating && parentGeneratingId) {
      setShowGenerateModal(true);
      return;
    }

    if (isThisUpdateGenerating && updateGeneratingId) {
      setShowGenerateModal(true);
      return;
    }

    setShowGenerateModal(true);
  }, [isThisUpdateGenerating, isParentGenerating, updateGeneratingId, parentGeneratingId, canGenerate, isDetectingFfmpeg]);

  const effectiveGenerating = isThisUpdateGenerating || isParentGenerating;

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
                <StoryVideoProgress
                  storyId={update.id}
                  video={update.generated_video}
                  story={update}
                  variant="compact"
                />
                {isParentGenerating && !update.generated_video && (
                  <StatusBadge label="Included in parent" variant="warning" />
                )}
              </div>
              <h3 className="font-semibold text-base mb-1">{cleanTitle}</h3>
              <StoryMeta story={update} />
              <StoryBody body={update.body} />
            </div>
            <div onClick={(e) => e.stopPropagation()}>
              <StoryActions
                hasVideo={hasVideo}
                generatedVideo={update.generated_video}
                permalink={update.permalink}
                onGenerate={handleGenerate}
                onUpload={() => setShowUploadModal(true)}
                onDelete={() => onDelete(update)}
                canGenerate={canGenerate}
                isDetectingFfmpeg={isDetectingFfmpeg}
                isGenerating={effectiveGenerating}
              />
            </div>
          </div>
        </div>
      </div>

      {showUploadModal && update.generated_video && (
        <UploadModal
          video={update.generated_video}
          onClose={() => setShowUploadModal(false)}
        />
      )}

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
