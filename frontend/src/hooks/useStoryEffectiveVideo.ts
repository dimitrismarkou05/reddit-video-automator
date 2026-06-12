import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ACTIVE_GENERATION_STATUSES,
  TERMINAL_VIDEO_STATUSES,
  isVideoGenerating,
} from "@/config/videoStatus";
import { useLiveGeneratedVideo } from "@/hooks/useLiveGeneratedVideo";
import { useStoryGenerationState } from "@/hooks/useStoryGenerationState";
import { videoApi } from "@/services/api";
import type { GeneratedVideo } from "@/types";

/**
 * Resolve the story's current video for badges/progress: cached generated_video,
 * an in-flight job not yet on the story payload, or live SSE/polling updates.
 */
export function useStoryEffectiveVideo(
  storyId: number,
  video: GeneratedVideo | null | undefined,
) {
  const { isGenerating, activeVideoId } = useStoryGenerationState(
    storyId,
    video,
  );

  const needsFetch = activeVideoId != null && !video;

  const { data: fetchedVideo, isError } = useQuery({
    queryKey: ["video", activeVideoId],
    queryFn: async () => {
      const { data } = await videoApi.get(activeVideoId!);
      return data as GeneratedVideo;
    },
    enabled: needsFetch,
    retry: false,
    refetchInterval: (query) => {
      const v = query.state.data as GeneratedVideo | undefined;
      if (!v) return 2000;
      if (isVideoGenerating(v) || ACTIVE_GENERATION_STATUSES.includes(v.status)) {
        return 2000;
      }
      return false;
    },
  });

  const baseVideo = useMemo(() => {
    if (!isGenerating) {
      if (video && TERMINAL_VIDEO_STATUSES.includes(video.status)) {
        return video;
      }
      return null;
    }
    return video ?? (isError ? null : fetchedVideo) ?? null;
  }, [isGenerating, video, fetchedVideo, isError]);

  const liveEnabled = !!baseVideo && isGenerating;
  const liveVideo = useLiveGeneratedVideo(baseVideo, liveEnabled);

  return useMemo(() => {
    if (!isGenerating) {
      if (video && TERMINAL_VIDEO_STATUSES.includes(video.status)) {
        return video;
      }
      return null;
    }
    return liveVideo;
  }, [isGenerating, video, liveVideo]);
}
