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
  isActivelyGenerating,
  className,
}: {
  story?: Pick<Story, "status">;
  isActivelyGenerating: boolean;
  className?: string;
}) {
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
  const isGenerating =
    isVideoGenerating(video) || ACTIVE_GENERATION_STATUSES.includes(video.status);

  return (
    <VideoStatusBadge
      video={video}
      showPercent={isGenerating}
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
    />
  );
}
