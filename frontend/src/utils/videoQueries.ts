import type { QueryClient } from "@tanstack/react-query";
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
