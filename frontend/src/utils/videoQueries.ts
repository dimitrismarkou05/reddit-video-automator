import type { QueryClient } from "@tanstack/react-query";
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
  const patch: VideoPatch = {
    status: "paused",
    is_paused: true,
    queue_position: null,
    progress_percent: video.progress_percent,
    current_step: video.current_step,
  };

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
    progress: video.progress_percent,
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
  const patch: VideoPatch = {
    status: "queued",
    is_paused: false,
    progress_percent: video.progress_percent,
    current_step: video.current_step,
  };

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
    progress: video.progress_percent,
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

function isRegressiveProgress(
  prev: MergeableProgress,
  next: MergeableProgress,
): boolean {
  if (TERMINAL_PROGRESS_STATUSES.includes(next.status)) return false;
  if (next.is_paused || next.status === "paused") return false;
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
    return next;
  }

  const prevPaused = prev.is_paused || prev.status === "paused";
  if (prevPaused) {
    if (next.is_paused || next.status === "paused") {
      return next;
    }
    if (isRegressiveProgress(prev, next)) {
      return null;
    }
    if (
      next.status !== "queued" &&
      next.status !== "processing" &&
      next.progress_percent < prev.progress_percent
    ) {
      return null;
    }
    return next;
  }

  if (isRegressiveProgress(prev, next)) {
    return null;
  }

  return next;
}

export function mergeGeneratedVideoProgress(
  base: GeneratedVideo,
  incoming: Partial<GeneratedVideo>,
): GeneratedVideo {
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
  return {
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

  queryClient.invalidateQueries({ queryKey: storyQueryKey(storyId) });
  queryClient.invalidateQueries({ queryKey: ["stories"] });
}
