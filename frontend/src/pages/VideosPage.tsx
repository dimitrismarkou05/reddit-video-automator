import { useEffect, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Film, Clock } from "lucide-react";
import { videoApi } from "@/services/api";
import { removeVideoFromCache } from "@/utils/videoQueries";
import { VideoCard } from "@/components/videos/VideoCard";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadingSpinner } from "@/components/common/LoadingSpinner";
import { PageHeader } from "@/components/common/PageHeader";
import { ACTIVE_GENERATION_STATUSES } from "@/config/videoStatus";
import type { GeneratedVideo } from "@/types";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

export function VideosPage() {
  const queryClient = useQueryClient();
  const {
    data: videos,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["videos"],
    queryFn: async () => {
      const { data } = await videoApi.list();
      return data as GeneratedVideo[];
    },
  });

  // Determine if any videos are actively generating
  const hasActiveGenerations = useMemo(() => {
    if (!videos) return false;
    return videos.some((v) => ACTIVE_GENERATION_STATUSES.includes(v.status));
  }, [videos]);

  // Use dynamic refetch interval - poll every 2s if there are active generations, otherwise 30s
  const { data: pollingVideos } = useQuery({
    queryKey: ["videos-polling"],
    queryFn: async () => {
      const { data } = await videoApi.list();
      return data as GeneratedVideo[];
    },
    refetchInterval: hasActiveGenerations ? 2000 : 30000,
    enabled: hasActiveGenerations,
  });

  const displayVideos = hasActiveGenerations
    ? (pollingVideos ?? videos)
    : videos;

  useEffect(() => {
    const url = `${API_BASE.replace("/api/v1", "")}/api/v1/sse/notifications`;
    const eventSource = new EventSource(url);
    const onVideoDeleted = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (data.video_id) {
          removeVideoFromCache(queryClient, data.video_id);
        }
      } catch {
        /* ignore */
      }
    };
    eventSource.addEventListener("video_deleted", onVideoDeleted);
    return () => {
      eventSource.removeEventListener("video_deleted", onVideoDeleted);
      eventSource.close();
    };
  }, [queryClient]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Generated Videos"
        actions={
          <button
            onClick={() => refetch()}
            className="cursor-pointer btn-secondary text-sm flex items-center gap-2"
          >
            <Clock className="w-4 h-4" />
            Refresh
          </button>
        }
      />

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <LoadingSpinner size="md" />
        </div>
      ) : displayVideos && displayVideos.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {displayVideos.map((video: GeneratedVideo) => (
            <VideoCard key={video.id} video={video} />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={Film}
          title="No videos yet"
          subtitle="Generate your first video from the Stories tab"
        />
      )}
    </div>
  );
}
