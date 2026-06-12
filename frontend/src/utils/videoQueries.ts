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
