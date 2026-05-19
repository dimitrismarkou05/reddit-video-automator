import { useState } from "react";
import {
  Film,
  Upload,
  BarChart3,
  Clock,
  Play,
  ExternalLink,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { STATUS_CONFIG, YT_STATUS_CONFIG } from "@/config/videoStatus";
import { UploadModal } from "@/components/UploadModal";
import { StatsModal } from "@/components/StatsModal";
import type { GeneratedVideo } from "@/types";

interface VideoCardProps {
  video: GeneratedVideo;
}

export function VideoCard({ video }: VideoCardProps) {
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

        <div className="absolute top-2 left-2 px-2 py-1 bg-black/70 text-white text-xs rounded-md font-medium">
          {video.format === "shorts" ? "9:16 Shorts" : "16:9 Normal"}
        </div>

        <div
          className={`absolute top-2 right-2 px-2 py-1 rounded-md text-xs font-medium flex items-center gap-1 ${status.bg} ${status.color}`}
        >
          <StatusIcon className="w-3 h-3" />
          {status.label}
        </div>

        {video.status === "processing" && (
          <div className="absolute bottom-0 left-0 right-0 h-1 bg-gray-700">
            <div
              className="h-full bg-primary transition-all duration-300"
              style={{ width: `${video.progress_percent}%` }}
            />
          </div>
        )}
      </div>

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

        <div className="flex items-center gap-2">
          {video.status === "done" &&
            video.youtube_upload_status === "not_uploaded" && (
              <button
                onClick={() => setShowUploadModal(true)}
                className="cursor-pointer flex-1 btn-primary text-xs py-2 flex items-center justify-center gap-1"
              >
                <Upload className="w-3 h-3" />
                Upload to YouTube
              </button>
            )}

          {video.youtube_upload_status === "uploaded" &&
            video.youtube_video_id && (
              <button
                onClick={() => setShowStatsModal(true)}
                className="cursor-pointer flex-1 btn-secondary text-xs py-2 flex items-center justify-center gap-1"
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
              className="p-2 rounded-lg bg-gray-100 dark:bg-surface-dark dark:border dark:border-border-dark hover:bg-gray-200 dark:hover:bg-white/5 transition-colors"
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
