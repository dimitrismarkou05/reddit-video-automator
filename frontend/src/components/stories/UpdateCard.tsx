import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Clock, Film } from "lucide-react";
import { BranchConnector } from "./BranchConnector";
import { StoryMeta } from "./StoryMeta";
import { StoryActions } from "./StoryActions";
import { StoryBody } from "./StoryBody";
import { StatusBadge } from "@/components/common/StatusBadge";
import { GenerateVideoModal } from "@/components/GenerateVideoModal";
import { stripUpdatePrefix } from "@/lib/formatters";
import type { Story } from "@/types";

interface UpdateCardProps {
  update: Story;
  index: number;
  totalUpdates: number;
  onDelete: (story: Story) => void;
  parentStoryId: number;
}

export function UpdateCard({
  update,
  index,
  totalUpdates,
  onDelete,
  parentStoryId,
}: UpdateCardProps) {
  const navigate = useNavigate();
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const hasVideo = !!update.generated_video;
  const showNumberBadge = totalUpdates > 1;
  const updateNumber = index + 1;
  const cleanTitle = stripUpdatePrefix(update.title);

  const handleCardClick = (e: React.MouseEvent) => {
    // Don't navigate if clicking on action buttons
    const target = e.target as HTMLElement;
    if (target.closest("button") || target.closest("a")) {
      return;
    }
    // Navigate to story detail with anchor to this update
    navigate(`/stories/${parentStoryId}#update-${update.id}`);
  };

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
              </div>
              <h3 className="font-semibold text-base mb-1">{cleanTitle}</h3>
              <StoryMeta story={update} />
              <StoryBody body={update.body} />
            </div>
            <div onClick={(e) => e.stopPropagation()}>
              <StoryActions
                hasVideo={hasVideo}
                permalink={update.permalink}
                onGenerate={() => setShowGenerateModal(true)}
                onDelete={() => onDelete(update)}
              />
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
