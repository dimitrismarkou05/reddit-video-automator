import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { isVideoGenerating, ACTIVE_GENERATION_STATUSES } from "@/config/videoStatus";
import { useVideoProgress } from "@/hooks/useVideoProgress";
import { videoApi } from "@/services/api";
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
    if (!progress) return base;

    const progressStatus =
      progress.status === "deleted" ? "cancelled" : progress.status;

    return {
      ...base,
      status: progressStatus,
      progress_percent: progress.progress_percent,
      current_step: progress.current_step,
      step_progress: progress.step_progress,
      queue_position: progress.queue_position ?? base.queue_position,
      is_paused: progress.is_paused,
      error_message: progress.error_message ?? base.error_message,
      thumbnail_path: progress.thumbnail_path ?? base.thumbnail_path,
    };
  }, [video, polledVideo, progress]);
}
