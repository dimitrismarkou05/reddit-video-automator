import { useMemo } from "react";
import {
  ACTIVE_GENERATION_STATUSES,
  TERMINAL_VIDEO_STATUSES,
  isVideoGenerating,
} from "@/config/videoStatus";
import { useVideoJobsStore } from "@/store/videoJobs";
import type { GeneratedVideo } from "@/types";

/** Whether a story currently has an in-flight generation (job store or live video record). */
export function useStoryGenerationState(
  storyId: number,
  generatedVideo?: GeneratedVideo | null,
) {
  const activeJob = useVideoJobsStore((s) => s.getJobForStory(storyId));

  return useMemo(() => {
    if (activeJob) {
      return { isGenerating: true, activeVideoId: activeJob.videoId };
    }

    const gv = generatedVideo;
    if (!gv || TERMINAL_VIDEO_STATUSES.includes(gv.status)) {
      return { isGenerating: false, activeVideoId: null };
    }

    const generating =
      isVideoGenerating(gv) || ACTIVE_GENERATION_STATUSES.includes(gv.status);

    return {
      isGenerating: generating,
      activeVideoId: generating ? gv.id : null,
    };
  }, [activeJob, generatedVideo]);
}
