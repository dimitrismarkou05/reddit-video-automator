import { useState } from "react";
import { ChevronDown, ChevronRight, GitBranch, Clock } from "lucide-react";
import { StoryMeta } from "./StoryMeta";
import { StoryActions } from "./StoryActions";
import { StoryBody } from "./StoryBody";
import { UpdateCard } from "./UpdateCard";
import { StatusBadge } from "@/components/common/StatusBadge";
import { GenerateVideoModal } from "@/components/GenerateVideoModal";
import type { Story } from "@/types";

interface StoryCardProps {
  story: Story;
  onDelete: (story: Story) => void;
}

export function StoryCard({ story, onDelete }: StoryCardProps) {
  const [showUpdates, setShowUpdates] = useState(false);
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const hasUpdates = story.updates && story.updates.length > 0;
  const hasVideo = !!story.generated_video;
  const updateCount = story.updates?.length || 0;

  return (
    <div className="space-y-0">
      <div className="card p-4 hover:shadow-md transition-shadow">
        <div className="flex items-start gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <StatusBadge label={`r/${story.subreddit}`} variant="primary" />
              {story.is_update && (
                <StatusBadge label="Update" variant="warning" />
              )}
              {hasVideo && (
                <StatusBadge
                  label="Video Ready"
                  icon={Clock}
                  variant="success"
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
                    <GitBranch className="w-3 h-3 text-primary mr-0.75" />
                  </button>
                </>
              )}
            </div>
            <h3 className="font-semibold text-base mb-1">{story.title}</h3>
            <StoryMeta story={story} />
            <StoryBody body={story.body} />
          </div>
          <StoryActions
            hasVideo={hasVideo}
            permalink={story.permalink}
            onGenerate={() => setShowGenerateModal(true)}
            onDelete={() => onDelete(story)}
          />
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
