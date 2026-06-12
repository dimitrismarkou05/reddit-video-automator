import type { GeneratedVideo, Story } from "@/types";

export const TERMINAL_VIDEO_STATUSES = ["done", "failed", "cancelled", "deleted"];

export const ACTIVE_GENERATION_STATUSES = [
  "queued",
  "preparing",
  "downloading_model",
  "initializing_pipeline",
  "generating_script",
  "tts",
  "tts_synthesizing",
  "tts_done",
  "transcribing",
  "transcribe_done",
  "generating_subtitles",
  "subtitles_done",
  "selecting_background",
  "compositing",
  "ffmpeg_processing",
  "compositing_done",
  "thumbnail",
  "generating_thumbnail",
  "uploading",
  "cleanup",
  "processing",
  "paused", // CRITICAL FIX: paused is an active state, not terminal
];

export const STATUS_CONFIG: Record<
  string,
  { label: string; color: string; bgColor: string }
> = {
  queued: {
    label: "Queued",
    color: "text-blue-600",
    bgColor: "bg-blue-100 dark:bg-blue-900/30",
  },
  preparing: {
    label: "Preparing",
    color: "text-blue-600",
    bgColor: "bg-blue-100 dark:bg-blue-900/30",
  },
  downloading_model: {
    label: "Downloading Model",
    color: "text-blue-600",
    bgColor: "bg-blue-100 dark:bg-blue-900/30",
  },
  initializing_pipeline: {
    label: "Initializing",
    color: "text-blue-600",
    bgColor: "bg-blue-100 dark:bg-blue-900/30",
  },
  generating_script: {
    label: "Script",
    color: "text-blue-600",
    bgColor: "bg-blue-100 dark:bg-blue-900/30",
  },
  tts: {
    label: "TTS",
    color: "text-purple-600",
    bgColor: "bg-purple-100 dark:bg-purple-900/30",
  },
  tts_synthesizing: {
    label: "Synthesizing",
    color: "text-purple-600",
    bgColor: "bg-purple-100 dark:bg-purple-900/30",
  },
  tts_done: {
    label: "TTS Done",
    color: "text-purple-600",
    bgColor: "bg-purple-100 dark:bg-purple-900/30",
  },
  transcribing: {
    label: "Transcribing",
    color: "text-indigo-600",
    bgColor: "bg-indigo-100 dark:bg-indigo-900/30",
  },
  transcribe_done: {
    label: "Transcribed",
    color: "text-indigo-600",
    bgColor: "bg-indigo-100 dark:bg-indigo-900/30",
  },
  generating_subtitles: {
    label: "Subtitles",
    color: "text-indigo-600",
    bgColor: "bg-indigo-100 dark:bg-indigo-900/30",
  },
  subtitles_done: {
    label: "Subtitles Done",
    color: "text-indigo-600",
    bgColor: "bg-indigo-100 dark:bg-indigo-900/30",
  },
  selecting_background: {
    label: "Background",
    color: "text-cyan-600",
    bgColor: "bg-cyan-100 dark:bg-cyan-900/30",
  },
  compositing: {
    label: "Compositing",
    color: "text-orange-600",
    bgColor: "bg-orange-100 dark:bg-orange-900/30",
  },
  ffmpeg_processing: {
    label: "FFmpeg",
    color: "text-orange-600",
    bgColor: "bg-orange-100 dark:bg-orange-900/30",
  },
  compositing_done: {
    label: "Finalizing",
    color: "text-orange-600",
    bgColor: "bg-orange-100 dark:bg-orange-900/30",
  },
  thumbnail: {
    label: "Thumbnail",
    color: "text-pink-600",
    bgColor: "bg-pink-100 dark:bg-pink-900/30",
  },
  generating_thumbnail: {
    label: "Thumbnail",
    color: "text-pink-600",
    bgColor: "bg-pink-100 dark:bg-pink-900/30",
  },
  uploading: {
    label: "Uploading",
    color: "text-green-600",
    bgColor: "bg-green-100 dark:bg-green-900/30",
  },
  cleanup: {
    label: "Cleanup",
    color: "text-gray-600",
    bgColor: "bg-gray-100 dark:bg-gray-900/30",
  },
  processing: {
    label: "Processing",
    color: "text-blue-600",
    bgColor: "bg-blue-100 dark:bg-blue-900/30",
  },
  done: {
    label: "Video Generated",
    color: "text-green-600",
    bgColor: "bg-green-100 dark:bg-green-900/30",
  },
  failed: {
    label: "Failed",
    color: "text-red-600",
    bgColor: "bg-red-100 dark:bg-red-900/30",
  },
  cancelled: {
    label: "Cancelled",
    color: "text-gray-600",
    bgColor: "bg-gray-100 dark:bg-gray-900/30",
  },
  paused: {
    label: "Paused",
    color: "text-yellow-600",
    bgColor: "bg-yellow-100 dark:bg-yellow-900/30",
  },
};

export const YT_STATUS_CONFIG: Record<
  string,
  { label: string; color: string; bgColor: string }
> = {
  not_uploaded: {
    label: "Not Uploaded",
    color: "text-neutral-700 dark:text-neutral-200",
    bgColor: "bg-neutral-100 dark:bg-neutral-700/70",
  },
  uploaded: {
    label: "Uploaded",
    color: "text-green-600",
    bgColor: "bg-green-100 dark:bg-green-900/30",
  },
  uploading: {
    label: "Uploading",
    color: "text-blue-600",
    bgColor: "bg-blue-100 dark:bg-blue-900/30",
  },
  failed: {
    label: "Upload Failed",
    color: "text-red-600",
    bgColor: "bg-red-100 dark:bg-red-900/30",
  },
  private: {
    label: "Private",
    color: "text-yellow-600",
    bgColor: "bg-yellow-100 dark:bg-yellow-900/30",
  },
  public: {
    label: "Public",
    color: "text-green-600",
    bgColor: "bg-green-100 dark:bg-green-900/30",
  },
  unlisted: {
    label: "Unlisted",
    color: "text-purple-600",
    bgColor: "bg-purple-100 dark:bg-purple-900/30",
  },
};

export type StoryStatusVariant =
  | "primary"
  | "success"
  | "warning"
  | "error"
  | "info"
  | "neutral";

/** Story statuses that imply a video record; stale when generated_video is missing. */
export const VIDEO_DERIVED_STORY_STATUSES = new Set([
  "video_processing",
  "video_queued",
  "video_paused",
  "video_done",
  "video_failed",
  "uploading",
  "uploaded",
  "upload_failed",
]);

export const STORY_STATUS_CONFIG: Record<
  string,
  { label: string; variant: StoryStatusVariant }
> = {
  fetched: { label: "Fetched", variant: "neutral" },
  stored: { label: "Stored", variant: "neutral" },
  update_linked: { label: "Update Linked", variant: "info" },
  ready_for_video: { label: "Ready to Generate", variant: "info" },
  video_processing: { label: "Generating...", variant: "warning" },
  video_queued: { label: "Queued", variant: "info" },
  video_paused: { label: "Paused", variant: "neutral" },
  video_cancelled: { label: "Cancelled", variant: "neutral" },
  video_done: { label: "Video Generated", variant: "success" },
  video_failed: { label: "Generation Failed", variant: "error" },
  uploading: { label: "Uploading...", variant: "warning" },
  uploaded: { label: "Uploaded", variant: "success" },
  upload_failed: { label: "Upload Failed", variant: "error" },
};

export function truncateTitle(title: string, maxLen = 60): string {
  if (title.length <= maxLen) return title;
  return `${title.slice(0, maxLen - 3)}...`;
}

const DISPLAY_STEP_BLOCKLIST = ["done", "failed", "cancelled", "deleted"];

export function getVideoDisplayKey(
  video: Pick<GeneratedVideo, "status" | "current_step"> & {
    progress_percent?: number;
  },
): string {
  if (video.status === "deleted") return "cancelled";

  if (video.status === "queued") {
    if (
      (video.progress_percent ?? 0) > 0 &&
      video.current_step &&
      video.current_step !== "queued" &&
      !DISPLAY_STEP_BLOCKLIST.includes(video.current_step)
    ) {
      return video.current_step;
    }
    return "queued";
  }

  const statusTerminal = ["done", "failed", "cancelled", "paused"];
  if (statusTerminal.includes(video.status)) {
    return video.status;
  }

  // "failed" is also a checkpoint step name — only trust it when status is failed.
  if (
    video.current_step &&
    !DISPLAY_STEP_BLOCKLIST.includes(video.current_step)
  ) {
    return video.current_step;
  }

  return video.status;
}

export function isVideoGenerating(video: Pick<GeneratedVideo, "status" | "current_step">): boolean {
  if (TERMINAL_VIDEO_STATUSES.includes(video.status)) return false;
  if (video.status === "paused" || video.status === "queued") return true;
  if (ACTIVE_GENERATION_STATUSES.includes(video.status)) return true;
  if (
    video.current_step &&
    !TERMINAL_VIDEO_STATUSES.includes(video.current_step) &&
    video.current_step !== "done"
  ) {
    return true;
  }
  return false;
}

export function getStepLabel(
  video: Pick<GeneratedVideo, "status" | "current_step">
): string {
  const key = getVideoDisplayKey(video);
  return STATUS_CONFIG[key]?.label ?? key.replace(/_/g, " ");
}

export function getStoryDisplayStatus(story: Story): {
  label: string;
  variant: StoryStatusVariant;
  displayKey: string;
  showPercent: boolean;
  progressPercent: number;
} {
  const gv = story.generated_video;
  if (gv) {
    const key = getVideoDisplayKey(gv);
    const config = STATUS_CONFIG[key] || STATUS_CONFIG.processing;
    if (gv.status === "done") {
      return {
        label: "Video Generated",
        variant: "success",
        displayKey: "done",
        showPercent: false,
        progressPercent: 100,
      };
    }
    if (gv.status === "failed") {
      return {
        label: "Generation Failed",
        variant: "error",
        displayKey: "failed",
        showPercent: false,
        progressPercent: gv.progress_percent,
      };
    }
    if (gv.status === "cancelled") {
      return {
        label: "Cancelled",
        variant: "neutral",
        displayKey: "cancelled",
        showPercent: false,
        progressPercent: gv.progress_percent,
      };
    }
    if (gv.status === "paused") {
      return {
        label: "Paused",
        variant: "neutral",
        displayKey: "paused",
        showPercent: false,
        progressPercent: gv.progress_percent,
      };
    }
    if (gv.status === "queued") {
      const pos = gv.queue_position ? ` #${gv.queue_position}` : "";
      return {
        label: `Queued${pos}`,
        variant: "info",
        displayKey: "queued",
        showPercent: false,
        progressPercent: gv.progress_percent,
      };
    }
    return {
      label: config.label,
      variant: "warning",
      displayKey: key,
      showPercent: true,
      progressPercent: gv.progress_percent,
    };
  }

  const statusKey = VIDEO_DERIVED_STORY_STATUSES.has(story.status)
    ? "ready_for_video"
    : story.status;
  const storyConfig = STORY_STATUS_CONFIG[statusKey] || {
    label: statusKey.replace(/_/g, " "),
    variant: "neutral" as StoryStatusVariant,
  };
  return {
    label: storyConfig.label,
    variant: storyConfig.variant,
    displayKey: statusKey,
    showPercent: false,
    progressPercent: 0,
  };
}
