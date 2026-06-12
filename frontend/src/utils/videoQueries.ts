import type { QueryClient } from "@tanstack/react-query";
import {
  applyPeakProgressPercent,
  clearVideoProgressSession,
  commitVideoProgress,
  getMergedVideoProgress,
  type VideoProgressData,
} from "@/store/videoProgressSession";
import { useVideoJobsStore } from "@/store/videoJobs";
import type { GeneratedVideo, Story } from "@/types";

export function storyQueryKey(storyId: number | string) {
  return ["story", Number(storyId)] as const;
}

export function removeVideoFromCache(
  queryClient: QueryClient,
  videoId: number,
) {
  for (const queryKey of [["videos"], ["videos-polling"]] as const) {
    queryClient.setQueryData<GeneratedVideo[]>(queryKey, (old) =>
      old?.filter((v) => v.id !== videoId),
    );
  }
}

export function invalidateVideos(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: ["videos"] });
  queryClient.invalidateQueries({ queryKey: ["videos-polling"] });
}

type VideoPatch = Partial<GeneratedVideo>;

function patchVideoInCaches(
  queryClient: QueryClient,
  videoId: number,
  patch: VideoPatch,
  storyId?: number,
) {
  for (const queryKey of [["videos"], ["videos-polling"]] as const) {
    queryClient.setQueryData<GeneratedVideo[]>(queryKey, (old) =>
      old?.map((v) => (v.id === videoId ? { ...v, ...patch } : v)),
    );
  }

  queryClient.setQueryData<GeneratedVideo>(["video", videoId], (old) =>
    old ? { ...old, ...patch } : old,
  );

  if (storyId != null) {
    const patchStory = (story: Story): Story => {
      const gv = story.generated_video;
      if (story.id !== storyId || !gv || gv.id !== videoId) {
        return story;
      }
      return {
        ...story,
        status:
          patch.status === "paused"
            ? "video_paused"
            : patch.status === "queued"
              ? "video_queued"
              : story.status,
        generated_video: { ...gv, ...patch },
      };
    };

    queryClient.setQueryData<Story>(storyQueryKey(storyId), (old) =>
      old ? patchStory(old) : old,
    );
    queryClient.setQueriesData<{ items?: Story[] }>(
      { queryKey: ["stories"] },
      (old) => {
        if (!old?.items) return old;
        return { ...old, items: old.items.map(patchStory) };
      },
    );
  }
}

export function optimisticallyPauseVideo(
  queryClient: QueryClient,
  video: GeneratedVideo,
  storyId?: number,
): () => void {
  const videoId = video.id;
  const progressPercent = applyPeakProgressPercent(
    videoId,
    video.progress_percent,
  );
  const patch: VideoPatch = {
    status: "paused",
    is_paused: true,
    queue_position: null,
    progress_percent: progressPercent,
    current_step: video.current_step,
  };

  ingestVideoProgress({
    video_id: videoId,
    status: "paused",
    progress_percent: progressPercent,
    current_step: video.current_step ?? "processing",
    step_progress: video.step_progress ?? 0,
    error_message: video.error_message,
    error_type: video.error_type,
    error_step: video.error_step,
    queue_position: null,
    is_paused: true,
    retry_count: video.retry_count ?? 0,
  });

  const prevVideos = queryClient.getQueryData<GeneratedVideo[]>(["videos"]);
  const prevPolling = queryClient.getQueryData<GeneratedVideo[]>([
    "videos-polling",
  ]);
  const prevVideo = queryClient.getQueryData<GeneratedVideo>(["video", videoId]);
  const prevStory =
    storyId != null
      ? queryClient.getQueryData<Story>(storyQueryKey(storyId))
      : undefined;
  const prevJob = useVideoJobsStore.getState().jobs[videoId];

  patchVideoInCaches(queryClient, videoId, patch, storyId);
  useVideoJobsStore.getState().updateJob(videoId, {
    status: "paused",
    isPaused: true,
    queuePosition: null,
    progress: progressPercent,
    currentStep: video.current_step,
  });

  return () => {
    queryClient.setQueryData(["videos"], prevVideos);
    queryClient.setQueryData(["videos-polling"], prevPolling);
    queryClient.setQueryData(["video", videoId], prevVideo);
    if (storyId != null) {
      queryClient.setQueryData(storyQueryKey(storyId), prevStory);
    }
    if (prevJob) {
      useVideoJobsStore.getState().updateJob(videoId, prevJob);
    }
  };
}

export function optimisticallyResumeVideo(
  queryClient: QueryClient,
  video: GeneratedVideo,
  storyId?: number,
): () => void {
  const videoId = video.id;
  const progressPercent = applyPeakProgressPercent(
    videoId,
    video.progress_percent,
  );
  const patch: VideoPatch = {
    status: "queued",
    is_paused: false,
    progress_percent: progressPercent,
    current_step: video.current_step,
  };

  ingestVideoProgress({
    video_id: videoId,
    status: "queued",
    progress_percent: progressPercent,
    current_step: video.current_step ?? "queued",
    step_progress: video.step_progress ?? 0,
    error_message: video.error_message,
    error_type: video.error_type,
    error_step: video.error_step,
    queue_position: video.queue_position,
    is_paused: false,
    retry_count: video.retry_count ?? 0,
  });

  const prevVideos = queryClient.getQueryData<GeneratedVideo[]>(["videos"]);
  const prevPolling = queryClient.getQueryData<GeneratedVideo[]>([
    "videos-polling",
  ]);
  const prevVideo = queryClient.getQueryData<GeneratedVideo>(["video", videoId]);
  const prevStory =
    storyId != null
      ? queryClient.getQueryData<Story>(storyQueryKey(storyId))
      : undefined;
  const prevJob = useVideoJobsStore.getState().jobs[videoId];

  patchVideoInCaches(queryClient, videoId, patch, storyId);
  useVideoJobsStore.getState().updateJob(videoId, {
    status: "queued",
    isPaused: false,
    progress: progressPercent,
    currentStep: video.current_step,
  });

  return () => {
    queryClient.setQueryData(["videos"], prevVideos);
    queryClient.setQueryData(["videos-polling"], prevPolling);
    queryClient.setQueryData(["video", videoId], prevVideo);
    if (storyId != null) {
      queryClient.setQueryData(storyQueryKey(storyId), prevStory);
    }
    if (prevJob) {
      useVideoJobsStore.getState().updateJob(videoId, prevJob);
    }
  };
}

export function isVideoPaused(
  video: Pick<GeneratedVideo, "status" | "is_paused">,
): boolean {
  return video.status === "paused" || !!video.is_paused;
}

/** Single merge point for SSE/REST progress — shared across all hook instances. */
export function ingestVideoProgress(
  data: VideoProgressData,
): VideoProgressData | null {
  const prev = getMergedVideoProgress(data.video_id);
  const merged = mergeVideoProgress(prev, data);
  if (!merged) return null;
  return commitVideoProgress(merged);
}

export type { VideoProgressData };

/** Pipeline step order — keep in sync with backend PROGRESS_STEP_ORDER. */
const PROGRESS_STEP_ORDER = [
  "queued",
  "preparing",
  "downloading_model",
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
  "generating_thumbnail",
  "done",
  "failed",
  "cancelled",
  "paused",
  "processing",
];

const TERMINAL_PROGRESS_STATUSES = ["done", "failed", "cancelled", "deleted"];

function progressStepIndex(step: string | null | undefined): number {
  if (!step) return 0;
  const idx = PROGRESS_STEP_ORDER.indexOf(step);
  return idx >= 0 ? idx : 0;
}

export interface MergeableProgress {
  status: string;
  progress_percent: number;
  current_step: string;
  step_progress?: number;
  queue_position?: number | null;
  status_message?: string | null;
  is_paused?: boolean;
  error_message?: string | null;
}

function allowsProgressReset(
  prev: MergeableProgress,
  next: MergeableProgress,
): boolean {
  if (TERMINAL_PROGRESS_STATUSES.includes(next.status)) return true;
  return (
    next.status === "queued" &&
    (next.progress_percent ?? 0) === 0 &&
    (prev.progress_percent ?? 0) > 0
  );
}

/** Mirror backend monotonic rule — overall % never decreases except explicit retry. */
function clampMonotonicProgress<T extends MergeableProgress>(
  prev: MergeableProgress,
  next: T,
): T {
  if (allowsProgressReset(prev, next)) return next;
  const prevPct = prev.progress_percent ?? 0;
  const nextPct = next.progress_percent ?? 0;
  if (nextPct < prevPct) {
    return { ...next, progress_percent: prevPct };
  }
  return next;
}

function isRegressiveProgress(
  prev: MergeableProgress,
  next: MergeableProgress,
): boolean {
  if (TERMINAL_PROGRESS_STATUSES.includes(next.status)) return false;
  if (next.is_paused || next.status === "paused") return false;
  if (allowsProgressReset(prev, next)) return false;
  if (
    next.current_step === prev.current_step &&
    next.progress_percent < prev.progress_percent
  ) {
    return true;
  }
  if (
    progressStepIndex(next.current_step) <
      progressStepIndex(prev.current_step) &&
    next.progress_percent <= prev.progress_percent
  ) {
    return true;
  }
  return false;
}

/** Merge progress events; reject stale/regressive updates while paused. */
export function mergeVideoProgress<T extends MergeableProgress>(
  prev: T | null | undefined,
  next: T,
): T | null {
  if (!prev) return next;

  if (TERMINAL_PROGRESS_STATUSES.includes(next.status)) {
    return next;
  }

  if (next.is_paused || next.status === "paused") {
    return clampMonotonicProgress(prev, {
      ...next,
      is_paused: true,
      status: "paused",
    });
  }

  const prevPaused = prev.is_paused || prev.status === "paused";
  if (prevPaused) {
    if (next.is_paused || next.status === "paused") {
      return clampMonotonicProgress(prev, {
        ...next,
        is_paused: true,
        status: "paused",
      });
    }
    // Resume: backend sets status queued + is_paused false (not stale pipeline events).
    if (next.is_paused === false && next.status === "queued") {
      return clampMonotonicProgress(prev, next);
    }
    return null;
  }

  if (isRegressiveProgress(prev, next)) {
    return null;
  }

  return clampMonotonicProgress(prev, next);
}

export function mergeGeneratedVideoProgress(
  base: GeneratedVideo,
  incoming: Partial<GeneratedVideo>,
): GeneratedVideo {
  const basePaused = isVideoPaused(base);
  const isResume =
    incoming.is_paused === false && incoming.status === "queued";

  if (incoming.is_paused || incoming.status === "paused") {
    incoming = { ...incoming, status: "paused", is_paused: true };
  } else if (basePaused && !isResume) {
    return {
      ...base,
      progress_percent: Math.max(
        base.progress_percent,
        incoming.progress_percent ?? base.progress_percent,
      ),
    };
  }

  const merged = mergeVideoProgress(
    {
      status: base.status,
      progress_percent: base.progress_percent,
      current_step: base.current_step,
      step_progress: base.step_progress,
      queue_position: base.queue_position,
      is_paused: base.is_paused,
      error_message: base.error_message,
    },
    {
      status: incoming.status ?? base.status,
      progress_percent: incoming.progress_percent ?? base.progress_percent,
      current_step: incoming.current_step ?? base.current_step,
      step_progress: incoming.step_progress ?? base.step_progress,
      queue_position:
        incoming.queue_position !== undefined
          ? incoming.queue_position
          : base.queue_position,
      is_paused: incoming.is_paused ?? base.is_paused,
      error_message: incoming.error_message ?? base.error_message,
    },
  );
  if (!merged) return base;

  const result: GeneratedVideo = {
    ...base,
    ...incoming,
    status: merged.status,
    progress_percent: merged.progress_percent,
    current_step: merged.current_step,
    step_progress: merged.step_progress ?? base.step_progress,
    queue_position: merged.queue_position ?? base.queue_position,
    is_paused: merged.is_paused ?? base.is_paused,
    error_message: merged.error_message ?? base.error_message,
  };

  if (isVideoPaused(result)) {
    result.status = "paused";
    result.is_paused = true;
  }

  return result;
}

export function removeVideoQuery(queryClient: QueryClient, videoId: number) {
  queryClient.removeQueries({ queryKey: ["video", videoId] });
}

/** Clear generated_video on a story in list/detail caches after cancel-delete. */
export function clearStoryGeneratedVideo(
  queryClient: QueryClient,
  storyId: number,
  options?: { storyStatus?: string },
) {
  const patchStory = (s: Story): Story => {
    if (s.id !== storyId) {
      return {
        ...s,
        updates: s.updates?.map((u) =>
          u.id === storyId
            ? {
                ...u,
                generated_video: null,
                ...(options?.storyStatus ? { status: options.storyStatus } : {}),
              }
            : u,
        ),
      };
    }
    return {
      ...s,
      generated_video: null,
      ...(options?.storyStatus ? { status: options.storyStatus } : {}),
    };
  };

  queryClient.setQueriesData<{ items?: Story[] }>(
    { queryKey: ["stories"] },
    (old) => {
      if (!old?.items) return old;
      return {
        ...old,
        items: old.items.map(patchStory),
      };
    },
  );
  queryClient.setQueryData<Story>(storyQueryKey(storyId), (old) =>
    old ? patchStory(old) : old,
  );
}

/** Sync React Query and Zustand after a video is cancelled or deleted. */
export function cleanupDeletedVideo(
  queryClient: QueryClient,
  params: {
    videoId: number;
    storyId: number;
    storyStatus?: string;
    invalidateVideoList?: boolean;
  },
) {
  const { videoId, storyId, storyStatus, invalidateVideoList } = params;

  removeVideoFromCache(queryClient, videoId);
  removeVideoQuery(queryClient, videoId);
  clearStoryGeneratedVideo(queryClient, storyId, {
    storyStatus,
  });

  if (invalidateVideoList) {
    invalidateVideos(queryClient);
  }

  useVideoJobsStore.getState().removeJobsForStory(storyId);
  clearVideoProgressSession(videoId);

  queryClient.invalidateQueries({ queryKey: storyQueryKey(storyId) });
  queryClient.invalidateQueries({ queryKey: ["stories"] });
}
