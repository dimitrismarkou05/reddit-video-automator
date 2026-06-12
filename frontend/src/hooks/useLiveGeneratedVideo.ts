import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  isVideoGenerating,
  ACTIVE_GENERATION_STATUSES,
  TERMINAL_VIDEO_STATUSES,
} from "@/config/videoStatus";
import { useVideoProgress } from "@/hooks/useVideoProgress";
import { videoApi } from "@/services/api";
import { useVideoJobsStore } from "@/store/videoJobs";
import type { GeneratedVideo } from "@/types";

/** Merge story cached video with live SSE + polling while generating. */
export function useLiveGeneratedVideo(
  video: GeneratedVideo | null | undefined,
  enabled = true,
) {
  const videoId = video?.id ?? null;
  const isActive =
    enabled &&
    !!video &&
    (isVideoGenerating(video) || ACTIVE_GENERATION_STATUSES.includes(video.status));

  const { progress } = useVideoProgress({
    videoId: isActive ? videoId : null,
  });

  const { job, modalOwnsProgress } = useVideoJobsStore((s) => ({
    job: videoId != null ? s.jobs[videoId] : undefined,
    modalOwnsProgress: videoId != null && s.activeModalVideoId === videoId,
  }));

  const { data: polledVideo } = useQuery({
    queryKey: ["video", videoId],
    queryFn: async () => {
      const { data } = await videoApi.get(videoId!);
      return data as GeneratedVideo;
    },
    enabled: isActive && videoId !== null,
    refetchInterval: 2000,
  });

  return useMemo(() => {
    if (!video) return null;
    if (progress?.status === "deleted") return null;

    const base = polledVideo ?? video;
    let merged: GeneratedVideo = base;

    if (progress) {
      const progressStatus =
        progress.status === "deleted" ? "cancelled" : progress.status;
      const paused = progress.is_paused || progressStatus === "paused";

      merged = {
        ...base,
        status: paused ? "paused" : progressStatus,
        progress_percent: progress.progress_percent,
        current_step: progress.current_step,
        step_progress: progress.step_progress,
        queue_position: progress.queue_position ?? base.queue_position,
        is_paused: progress.is_paused,
        error_message: progress.error_message ?? base.error_message,
        thumbnail_path: progress.thumbnail_path ?? base.thumbnail_path,
      };
    }

    if (
      modalOwnsProgress &&
      job &&
      !TERMINAL_VIDEO_STATUSES.includes(job.status)
    ) {
      merged = {
        ...merged,
        status: job.isPaused ? "paused" : job.status,
        progress_percent: job.progress,
        current_step: job.currentStep,
        queue_position: job.queuePosition ?? merged.queue_position,
        is_paused: job.isPaused,
        error_message: job.errorMessage ?? merged.error_message,
      };
    }

    return merged;
  }, [video, polledVideo, progress, job, modalOwnsProgress]);
}
