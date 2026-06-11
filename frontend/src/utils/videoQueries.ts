import type { QueryClient } from "@tanstack/react-query";
import type { GeneratedVideo, Story } from "@/types";

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

/** Clear generated_video on a story in list/detail caches after cancel-delete. */
export function clearStoryGeneratedVideo(
  queryClient: QueryClient,
  storyId: number,
) {
  queryClient.setQueriesData<{ items?: Story[] }>(
    { queryKey: ["stories"] },
    (old) => {
      if (!old?.items) return old;
      return {
        ...old,
        items: old.items.map((s) =>
          s.id === storyId ? { ...s, generated_video: null } : s,
        ),
      };
    },
  );
  queryClient.setQueryData<Story>(["story", storyId], (old) =>
    old ? { ...old, generated_video: null } : old,
  );
}
