import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Film,
  Upload,
  BarChart3,
  Play,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  ExternalLink,
  Globe,
} from "lucide-react";
import { videoApi } from "@/services/api";
import { UploadModal } from "@/components/UploadModal";
import { StatsModal } from "@/components/StatsModal";
import type { GeneratedVideo } from "@/types";
import { formatDistanceToNow } from "date-fns";

const STATUS_CONFIG = {
  processing: {
    icon: Film,
    color: "text-blue-500",
    bg: "bg-blue-100 dark:bg-blue-900/30",
    label: "Processing",
  },
  done: {
    icon: CheckCircle,
    color: "text-green-500",
    bg: "bg-green-100 dark:bg-green-900/30",
    label: "Ready",
  },
  failed: {
    icon: XCircle,
    color: "text-red-500",
    bg: "bg-red-100 dark:bg-red-900/30",
    label: "Failed",
  },
  uploading: {
    icon: Upload,
    color: "text-yellow-500",
    bg: "bg-yellow-100 dark:bg-yellow-900/30",
    label: "Uploading",
  },
  uploaded: {
    icon: Globe,
    color: "text-green-500",
    bg: "bg-green-100 dark:bg-green-900/30",
    label: "Uploaded",
  },
  upload_failed: {
    icon: AlertCircle,
    color: "text-red-500",
    bg: "bg-red-100 dark:bg-red-900/30",
    label: "Upload Failed",
  },
};

const YT_STATUS_CONFIG = {
  not_uploaded: { color: "text-gray-400", label: "Not Uploaded" },
  uploading: { color: "text-yellow-500", label: "Uploading..." },
  uploaded: { color: "text-green-500", label: "Live on YouTube" },
  upload_failed: { color: "text-red-500", label: "Upload Failed" },
};

function VideoCard({ video }: { video: GeneratedVideo }) {
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showStatsModal, setShowStatsModal] = useState(false);
  const status =
    STATUS_CONFIG[video.status as keyof typeof STATUS_CONFIG] ||
    STATUS_CONFIG.processing;
  const ytStatus =
    YT_STATUS_CONFIG[
      video.youtube_upload_status as keyof typeof YT_STATUS_CONFIG
    ] || YT_STATUS_CONFIG.not_uploaded;
  const StatusIcon = status.icon;

  return (
    <div className="card overflow-hidden">
      {/* Thumbnail */}
      <div className="relative aspect-video bg-gray-900">
        {video.thumbnail_path ? (
          <img
            src={`file://${video.thumbnail_path}`}
            alt={video.story?.title || "Video thumbnail"}
            className="w-full h-full object-cover"
            onError={(e) => {
              (e.target as HTMLImageElement).src = "";
            }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Film className="w-12 h-12 text-gray-600" />
          </div>
        )}

        {/* Format badge */}
        <div className="absolute top-2 left-2 px-2 py-1 bg-black/70 text-white text-xs rounded-md font-medium">
          {video.format === "shorts" ? "9:16 Shorts" : "16:9 Normal"}
        </div>

        {/* Status badge */}
        <div
          className={`absolute top-2 right-2 px-2 py-1 rounded-md text-xs font-medium flex items-center gap-1 ${status.bg} ${status.color}`}
        >
          <StatusIcon className="w-3 h-3" />
          {status.label}
        </div>

        {/* Progress bar for processing */}
        {video.status === "processing" && (
          <div className="absolute bottom-0 left-0 right-0 h-1 bg-gray-700">
            <div
              className="h-full bg-primary transition-all duration-300"
              style={{ width: `${video.progress_percent}%` }}
            />
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-4">
        <h3 className="font-semibold text-sm mb-1 line-clamp-2">
          {video.story?.title || "Untitled Video"}
        </h3>

        <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400 mb-3">
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {formatDistanceToNow(new Date(video.created_at), {
              addSuffix: true,
            })}
          </span>
          {video.duration_seconds && (
            <span className="flex items-center gap-1">
              <Play className="w-3 h-3" />
              {Math.floor(video.duration_seconds / 60)}:
              {String(Math.floor(video.duration_seconds % 60)).padStart(2, "0")}
            </span>
          )}
        </div>

        {/* YouTube status */}
        <div className="flex items-center justify-between mb-3">
          <span className={`text-xs font-medium ${ytStatus.color}`}>
            {ytStatus.label}
          </span>
          {video.youtube_video_id && (
            <span className="text-xs text-gray-400 font-mono">
              {video.youtube_video_id}
            </span>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {video.status === "done" &&
            video.youtube_upload_status === "not_uploaded" && (
              <button
                onClick={() => setShowUploadModal(true)}
                className="flex-1 btn-primary text-xs py-2 flex items-center justify-center gap-1"
              >
                <Upload className="w-3 h-3" />
                Upload to YouTube
              </button>
            )}

          {video.youtube_upload_status === "uploaded" &&
            video.youtube_video_id && (
              <button
                onClick={() => setShowStatsModal(true)}
                className="flex-1 btn-secondary text-xs py-2 flex items-center justify-center gap-1"
              >
                <BarChart3 className="w-3 h-3" />
                Statistics
              </button>
            )}

          {video.youtube_video_id && (
            <a
              href={`https://youtube.com/watch?v=${video.youtube_video_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="p-2 rounded-lg bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
              title="Open on YouTube"
            >
              <ExternalLink className="w-4 h-4" />
            </a>
          )}
        </div>
      </div>

      {showUploadModal && (
        <UploadModal video={video} onClose={() => setShowUploadModal(false)} />
      )}
      {showStatsModal && (
        <StatsModal
          videoId={video.youtube_video_id!}
          onClose={() => setShowStatsModal(false)}
        />
      )}
    </div>
  );
}

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
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Generated Videos</h2>
        <button
          onClick={() => refetch()}
          className="btn-secondary text-sm flex items-center gap-2"
        >
          <Clock className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      ) : videos && videos.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {videos.map((video: GeneratedVideo) => (
            <VideoCard key={video.id} video={video} />
          ))}
        </div>
      ) : (
        <div className="card p-12 text-center">
          <Film className="w-12 h-12 mx-auto mb-4 text-gray-300" />
          <h3 className="text-lg font-semibold text-gray-500">No videos yet</h3>
          <p className="text-sm text-gray-400 mt-1">
            Generate your first video from the Stories tab
          </p>
        </div>
      )}
    </div>
  );
}
