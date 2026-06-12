import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  isVideoGenerating,
  ACTIVE_GENERATION_STATUSES,
  TERMINAL_VIDEO_STATUSES,
} from "@/config/videoStatus";
import { useVideoProgress } from "@/hooks/useVideoProgress";
import { videoApi } from "@/services/api";
import {
  applyPeakProgressPercent,
  getPeakProgressPercent,
  seedPeakProgressPercent,
} from "@/store/videoProgressSession";
import { mergeGeneratedVideoProgress } from "@/utils/videoQueries";
import { useVideoJobsStore } from "@/store/videoJobs";
import type { GeneratedVideo } from "@/types";

function withPeak(video: GeneratedVideo): GeneratedVideo {
  const peak = applyPeakProgressPercent(
    video.id,
    Math.max(video.progress_percent, getPeakProgressPercent(video.id)),
  );
  return peak === video.progress_percent
    ? video
    : { ...video, progress_percent: peak };
}

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

  useEffect(() => {
    if (videoId != null && video && video.progress_percent > 0) {
      seedPeakProgressPercent(videoId, video.progress_percent);
    }
  }, [videoId, video?.progress_percent]);

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
    enabled: isActive && videoId !== null && !progress,
    refetchInterval: progress ? false : 2000,
  });

  return useMemo(() => {
    if (!video) return null;
    if (progress?.status === "deleted") return null;

    const seededVideo = withPeak(video);
    const base =
      polledVideo && !progress
        ? mergeGeneratedVideoProgress(seededVideo, polledVideo)
        : seededVideo;
    let merged: GeneratedVideo = base;

    if (progress) {
      const progressStatus =
        progress.status === "deleted" ? "cancelled" : progress.status;
      const paused = progress.is_paused || progressStatus === "paused";

      const fromProgress = mergeGeneratedVideoProgress(merged, {
        status: paused ? "paused" : progressStatus,
        progress_percent: progress.progress_percent,
        current_step: progress.current_step,
        step_progress: progress.step_progress,
        queue_position: progress.queue_position ?? base.queue_position,
        is_paused: progress.is_paused,
        error_message: progress.error_message ?? base.error_message,
      });
      merged = {
        ...fromProgress,
        thumbnail_path: progress.thumbnail_path ?? fromProgress.thumbnail_path,
      };
    }

    if (job && !TERMINAL_VIDEO_STATUSES.includes(job.status)) {
      if (job.isPaused) {
        merged = mergeGeneratedVideoProgress(merged, {
          status: "paused",
          is_paused: true,
          progress_percent: Math.max(job.progress, merged.progress_percent),
          current_step: job.currentStep ?? merged.current_step,
        });
      } else if (modalOwnsProgress) {
        merged = mergeGeneratedVideoProgress(merged, {
          status: job.status,
          progress_percent: Math.max(job.progress, merged.progress_percent),
          current_step: job.currentStep,
          queue_position: job.queuePosition ?? merged.queue_position,
          is_paused: false,
          error_message: job.errorMessage ?? merged.error_message,
        });
      }
    }

    return withPeak(merged);
  }, [video, polledVideo, progress, job, modalOwnsProgress]);
}
