import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { cleanupDeletedVideo } from "@/utils/videoQueries";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

/** Keep story/video caches in sync when a video is cancelled or deleted elsewhere. */
export function useVideoDeletedNotifications(storyId?: number | null) {
  const queryClient = useQueryClient();

  useEffect(() => {
    const url = `${API_BASE.replace("/api/v1", "")}/api/v1/sse/notifications`;
    const eventSource = new EventSource(url);

    const onVideoDeleted = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as {
          video_id?: number;
          story_id?: number;
        };
        if (!data.video_id) return;

        const affectedStoryId = data.story_id ?? storyId;
        if (affectedStoryId != null) {
          cleanupDeletedVideo(queryClient, {
            videoId: data.video_id,
            storyId: affectedStoryId,
            storyStatus: "video_cancelled",
          });
        }
      } catch {
        /* ignore malformed payloads */
      }
    };

    eventSource.addEventListener("video_deleted", onVideoDeleted);
    return () => {
      eventSource.removeEventListener("video_deleted", onVideoDeleted);
      eventSource.close();
    };
  }, [queryClient, storyId]);
}
