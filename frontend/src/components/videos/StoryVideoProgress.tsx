import { StatusBadge } from "@/components/common/StatusBadge";
import { VideoGenerationProgress } from "@/components/videos/VideoGenerationProgress";
import { VideoStatusBadge } from "@/components/videos/VideoStatusBadge";
import {
  getStoryDisplayStatus,
  isVideoGenerating,
  ACTIVE_GENERATION_STATUSES,
} from "@/config/videoStatus";
import { useStoryEffectiveVideo } from "@/hooks/useStoryEffectiveVideo";
import { useStoryGenerationState } from "@/hooks/useStoryGenerationState";
import { isVideoPaused } from "@/utils/videoQueries";
import { useVideoJobsStore } from "@/store/videoJobs";
import type { GeneratedVideo, Story } from "@/types";

const BADGE_ALIGN = "shrink-0 self-center";

interface StoryVideoProgressProps {
  storyId: number;
  video: GeneratedVideo | null | undefined;
  className?: string;
  /** compact: pill on story cards | step: step bar under detail actions | badge: sidebar pill */
  variant?: "default" | "compact" | "step" | "badge";
  /** Required when no video exists so we can show Ready to Generate, etc. */
  story?: Pick<Story, "status">;
}

function StoryStatusFallback({
  story,
  storyId,
  isActivelyGenerating,
  className,
}: {
  story?: Pick<Story, "status">;
  storyId: number;
  isActivelyGenerating: boolean;
  className?: string;
}) {
  const activeJob = useVideoJobsStore((s) => s.getJobForStory(storyId));

  if (isActivelyGenerating && activeJob) {
    return (
      <VideoStatusBadge
        video={{
          status: activeJob.status,
          current_step: activeJob.currentStep,
          progress_percent: activeJob.progress,
          queue_position: activeJob.queuePosition,
          is_paused: activeJob.isPaused,
        }}
        showPercent
        className={className}
      />
    );
  }

  if (isActivelyGenerating) {
    return (
      <StatusBadge
        label="Generating..."
        variant="warning"
        className={className}
      />
    );
  }
  if (!story) return null;

  const displayStatus = getStoryDisplayStatus({
    ...story,
    generated_video: undefined,
  } as Story);

  return (
    <StatusBadge
      label={displayStatus.label}
      variant={displayStatus.variant}
      className={className}
    />
  );
}

function StoryVideoBadge({
  video,
  className,
}: {
  video: GeneratedVideo;
  className?: string;
}) {
  const isPaused = isVideoPaused(video);
  const isGenerating =
    !isPaused &&
    (isVideoGenerating(video) || ACTIVE_GENERATION_STATUSES.includes(video.status));

  return (
    <VideoStatusBadge
      video={video}
      showPercent={isGenerating || isPaused}
      className={className}
    />
  );
}

/** Live video status shared across stories list, detail, and updates. */
export function StoryVideoProgress({
  storyId,
  video,
  className = "",
  variant = "default",
  story,
}: StoryVideoProgressProps) {
  const { isGenerating } = useStoryGenerationState(storyId, video);
  const effectiveVideo = useStoryEffectiveVideo(storyId, video);
  const badgeClass = `${BADGE_ALIGN} ${className}`.trim();

  if (variant === "badge" || variant === "compact") {
    if (effectiveVideo) {
      return <StoryVideoBadge video={effectiveVideo} className={badgeClass} />;
    }
    return (
      <StoryStatusFallback
        story={story}
        storyId={storyId}
        isActivelyGenerating={isGenerating}
        className={badgeClass}
      />
    );
  }

  if (!effectiveVideo) return null;

  return (
    <VideoGenerationProgress
      video={effectiveVideo}
      className={className}
      variant={variant === "step" ? "step" : "inline"}
      showStepPercent={variant === "step"}
    />
  );
}
