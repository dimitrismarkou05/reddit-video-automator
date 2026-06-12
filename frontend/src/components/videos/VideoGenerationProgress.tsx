import {
  ACTIVE_GENERATION_STATUSES,
  getStepLabel,
  isVideoGenerating,
} from "@/config/videoStatus";
import { isVideoPaused } from "@/utils/videoQueries";
import { VideoStatusBadge } from "@/components/videos/VideoStatusBadge";
import type { GeneratedVideo } from "@/types";

interface VideoGenerationProgressProps {
  video: GeneratedVideo;
  /** inline: badge + step bar | step: step bar only | card: stacked | compact: pill badge */
  variant?: "inline" | "step" | "card" | "compact";
  /** Append live (N%) next to step label — story detail step bar only */
  showStepPercent?: boolean;
  className?: string;
}

export function VideoGenerationProgress({
  video,
  variant = "inline",
  showStepPercent = false,
  className = "",
}: VideoGenerationProgressProps) {
  const isPaused = isVideoPaused(video);
  const isGenerating =
    !isPaused &&
    (isVideoGenerating(video) || ACTIVE_GENERATION_STATUSES.includes(video.status));
  const stepLabel = getStepLabel(video);

  if (variant === "compact") {
    return (
      <VideoStatusBadge
        video={video}
        showPercent={isGenerating || isPaused}
        className={`shrink-0 self-center ${className}`}
      />
    );
  }

  if (variant === "step") {
    if (isPaused) {
      return (
        <div className={`w-full max-w-md ${className}`}>
          <span className="text-xs text-yellow-600 dark:text-yellow-400">
            Paused — {stepLabel}
            {showStepPercent ? ` (${video.progress_percent}%)` : ""}
          </span>
          <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full mt-1 overflow-hidden">
            <div
              className="h-full bg-yellow-500 rounded-full"
              style={{ width: `${video.progress_percent}%` }}
            />
          </div>
        </div>
      );
    }
    if (isGenerating) {
      return (
        <div className={`w-full max-w-md ${className}`}>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {stepLabel}
            {showStepPercent ? ` (${video.progress_percent}%)` : ""}
            {video.queue_position ? ` (Queue #${video.queue_position})` : ""}
          </span>
          <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full mt-1 overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-500"
              style={{ width: `${video.progress_percent}%` }}
            />
          </div>
        </div>
      );
    }
    return null;
  }

  if (variant === "card") {
    return (
      <div className={`space-y-2 ${className}`}>
        <VideoStatusBadge video={video} />
        {isPaused && (
          <>
            <span className="text-xs text-yellow-600 dark:text-yellow-400 block">
              Paused — {stepLabel}
            </span>
            <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-yellow-500 rounded-full"
                style={{ width: `${video.progress_percent}%` }}
              />
            </div>
          </>
        )}
        {isGenerating && (
          <>
            <span className="text-xs text-gray-500 dark:text-gray-400 block">
              {stepLabel}
              {video.queue_position ? ` (Queue #${video.queue_position})` : ""}
            </span>
            <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-primary rounded-full transition-all duration-500"
                style={{ width: `${video.progress_percent}%` }}
              />
            </div>
          </>
        )}
      </div>
    );
  }

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <VideoStatusBadge video={video} showPercent={isGenerating || isPaused} />
      {isPaused && (
        <div className="w-full max-w-md">
          <span className="text-xs text-yellow-600 dark:text-yellow-400">
            Paused — {stepLabel}
          </span>
          <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full mt-1 overflow-hidden">
            <div
              className="h-full bg-yellow-500 rounded-full"
              style={{ width: `${video.progress_percent}%` }}
            />
          </div>
        </div>
      )}
      {isGenerating && (
        <div className="w-full max-w-md">
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {stepLabel}
            {video.queue_position ? ` (Queue #${video.queue_position})` : ""}
          </span>
          <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full mt-1 overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-500"
              style={{ width: `${video.progress_percent}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
