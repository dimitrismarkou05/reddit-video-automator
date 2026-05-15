import { useQuery } from "@tanstack/react-query";
import { Film, Clock } from "lucide-react";
import { videoApi } from "@/services/api";
import { VideoCard } from "@/components/videos/VideoCard";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadingSpinner } from "@/components/common/LoadingSpinner";
import { PageHeader } from "@/components/common/PageHeader";
import type { GeneratedVideo } from "@/types";

export function VideosPage() {
  const {
    data: videos,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["videos"],
    queryFn: async () => {
      const { data } = await videoApi.list();
      return data;
    },
  });

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
      ) : videos && videos.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {videos.map((video: GeneratedVideo) => (
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
