import { useState } from "react";
import {
  Film,
  Upload,
  BarChart3,
  Clock,
  Play,
  ExternalLink,
  Pause,
  X,
  Loader2,
  Trash2,
  AlertTriangle,
  CheckCircle,
  XCircle,
  MinusCircle,
  CircleDot,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import {
  STATUS_CONFIG,
  YT_STATUS_CONFIG,
  ACTIVE_GENERATION_STATUSES,
} from "@/config/videoStatus";
import { videoApi } from "@/services/api";
import type { GeneratedVideo } from "@/types";
import toast from "react-hot-toast";
import { useQueryClient } from "@tanstack/react-query";
import { removeVideoFromCache } from "@/utils/videoQueries";
import { useVideoJobsStore } from "@/store/videoJobs";

const STEP_LABELS: Record<string, string> = {
  queued: "Queued",
  preparing: "Preparing...",
  tts: "Generating speech...",
  tts_done: "TTS complete",
  transcribe_done: "Transcription complete",
  subtitles_done: "Subtitles done",
  selecting_background: "Selecting background...",
  compositing: "Compositing...",
  compositing_done: "Finalizing...",
  thumbnail: "Thumbnail...",
  done: "Ready",
  failed: "Failed",
  cancelled: "Cancelled",
  paused: "Paused",
};

// Map status to an appropriate icon since STATUS_CONFIG doesn't include icons
function getStatusIcon(status: string) {
  switch (status) {
    case "done":
      return CheckCircle;
    case "failed":
      return XCircle;
    case "cancelled":
      return MinusCircle;
    case "paused":
      return Pause;
    case "queued":
      return CircleDot;
    default:
      return Loader2;
  }
}

interface VideoCardProps {
  video: GeneratedVideo;
}

export function VideoCard({ video }: VideoCardProps) {
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showStatsModal, setShowStatsModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [imgError, setImgError] = useState(false);
  const queryClient = useQueryClient();
  const removeJob = useVideoJobsStore((s) => s.removeJob);

  const status = STATUS_CONFIG[video.status] || STATUS_CONFIG.processing;
  const ytStatus =
    YT_STATUS_CONFIG[video.youtube_upload_status] ||
    YT_STATUS_CONFIG.not_uploaded;
  const StatusIcon = getStatusIcon(video.status);
  const isGenerating = ACTIVE_GENERATION_STATUSES.includes(video.status);
  const isPaused = video.status === "paused";
  const isTerminal = ["done", "failed", "cancelled"].includes(video.status);
  const stepLabel = STEP_LABELS[video.current_step] || video.current_step;

  const handlePause = async () => {
    try {
      await videoApi.pause(video.id);
      toast.success("Paused");
      queryClient.invalidateQueries({ queryKey: ["videos"] });
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to pause");
    }
  };

  const handleResume = async () => {
    try {
      await videoApi.resume(video.id);
      toast.success("Resuming...");
      queryClient.invalidateQueries({ queryKey: ["videos"] });
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to resume");
    }
  };

  const handleCancel = async () => {
    if (isCancelling) return;
    setIsCancelling(true);
    try {
      await videoApi.cancel(video.id);
      removeVideoFromCache(queryClient, video.id);
      removeJob(video.id);
      toast("Generation cancelled", { icon: "⚠️" });
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to cancel");
      setIsCancelling(false);
    }
  };

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await videoApi.delete(video.id);
      toast.success("Video deleted");
      queryClient.invalidateQueries({ queryKey: ["videos"] });
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to delete");
    } finally {
      setIsDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  // Build class strings from STATUS_CONFIG (uses bgColor, not bg)
  const statusBadgeClasses = `${status.bgColor} ${status.color}`;

  return (
    <div className="card overflow-hidden">
      {/* Thumbnail */}
      <div className="relative aspect-video bg-neutral-900">
        {video.thumbnail_path && video.status === "done" && !imgError ? (
          <img
            src={`file://${video.thumbnail_path}`}
            alt={video.story?.title || "Video thumbnail"}
            className="w-full h-full object-cover"
            onError={() => setImgError(true)}
          />
        ) : video.status === "failed" ? (
          <div className="w-full h-full flex flex-col items-center justify-center bg-red-900/10">
            <AlertTriangle className="w-10 h-10 text-red-500 mb-2" />
            <span className="text-xs text-red-400 font-medium">
              Generation Failed
            </span>
          </div>
        ) : isCancelling ? (
          <div className="w-full h-full flex flex-col items-center justify-center">
            <Loader2 className="w-10 h-10 text-red-500 animate-spin mb-2" />
            <span className="text-xs text-red-500 font-medium">Cancelling...</span>
          </div>
        ) : isGenerating ? (
          <div className="w-full h-full flex flex-col items-center justify-center">
            <Loader2 className="w-10 h-10 text-gray-500 animate-spin mb-2" />
            <span className="text-xs text-gray-500">Generating...</span>
          </div>
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center">
            <Film className="w-10 h-10 text-gray-600 mb-2" />
            <span className="text-xs text-gray-500">
              {video.status === "cancelled" ? "Cancelled" : "No preview"}
            </span>
          </div>
        )}

        {/* Format badge */}
        <div className="absolute top-2 left-2 px-2 py-1 bg-black/70 text-white text-xs rounded-md font-medium">
          {video.format === "shorts" ? "9:16 Shorts" : "16:9 Normal"}
        </div>

        {/* Status badge */}
        <div
          className={`absolute top-2 right-2 px-2 py-1 rounded-md text-xs font-medium flex items-center gap-1 ${statusBadgeClasses}`}
        >
          <StatusIcon className="w-3 h-3" />
          {status.label}
        </div>

        {/* Progress bar overlay */}
        {isGenerating && (
          <div className="absolute bottom-0 left-0 right-0 h-1.5 bg-gray-700">
            <div
              className="h-full bg-primary transition-all duration-500"
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

        {/* Subreddit badge */}
        {video.story?.subreddit && (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary mb-2">
            r/{video.story.subreddit}
          </span>
        )}

        {/* Step indicator */}
        {isGenerating && (
          <div className="mb-2">
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {stepLabel}
              {video.queue_position ? ` (Queue #${video.queue_position})` : ""}
            </span>
            {/* Simple progress bar since ProgressBar component may not exist */}
            <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full mt-1 overflow-hidden">
              <div
                className="h-full bg-primary rounded-full transition-all duration-500"
                style={{ width: `${video.progress_percent}%` }}
              />
            </div>
          </div>
        )}

        {/* Error display */}
        {video.status === "failed" && video.error_message && (
          <div className="mb-2 p-2 bg-red-50 dark:bg-red-900/20 rounded-lg">
            <p className="text-xs text-red-600 dark:text-red-400">
              {video.error_message}
            </p>
          </div>
        )}

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

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          {/* Generating: Pause / Cancel */}
          {isGenerating && !isPaused && (
            <>
              <button
                onClick={handlePause}
                className="cursor-pointer flex-1 btn-secondary text-xs py-2 flex items-center justify-center gap-1"
              >
                <Pause className="w-3 h-3" />
                Pause
              </button>
              <button
                onClick={handleCancel}
                disabled={isCancelling}
                className="cursor-pointer px-3 py-2 bg-red-50 dark:bg-red-900/20 text-red-500 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 text-xs flex items-center gap-1 disabled:opacity-50"
              >
                {isCancelling ? (
                  <>
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Cancelling...
                  </>
                ) : (
                  <>
                    <X className="w-3 h-3" />
                    Cancel
                  </>
                )}
              </button>
            </>
          )}

          {/* Paused: Resume / Cancel */}
          {isPaused && (
            <>
              <button
                onClick={handleResume}
                disabled={isCancelling}
                className="cursor-pointer flex-1 btn-primary text-xs py-2 flex items-center justify-center gap-1 disabled:opacity-50"
              >
                <Play className="w-3 h-3" />
                Resume
              </button>
              <button
                onClick={handleCancel}
                disabled={isCancelling}
                className="cursor-pointer px-3 py-2 bg-red-50 dark:bg-red-900/20 text-red-500 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 text-xs flex items-center gap-1 disabled:opacity-50"
              >
                {isCancelling ? (
                  <>
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Cancelling...
                  </>
                ) : (
                  <>
                    <X className="w-3 h-3" />
                    Cancel
                  </>
                )}
              </button>
            </>
          )}

          {/* Done: Upload / YouTube link */}
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
              className="p-2 rounded-lg bg-gray-100 dark:bg-surface-dark dark:border dark:border-border-dark hover:bg-gray-200 dark:hover:bg-white/5"
              title="Open on YouTube"
            >
              <ExternalLink className="w-4 h-4" />
            </a>
          )}

          {/* Terminal states: Delete */}
          {isTerminal && (
            <button
              onClick={() => setShowDeleteConfirm(true)}
              disabled={isDeleting}
              className="cursor-pointer p-2 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/30 disabled:opacity-50"
              title="Delete video"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Delete confirmation dialog */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-surface-light dark:bg-surface-dark rounded-2xl w-full max-w-md shadow-xl p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-red-500" />
              </div>
              <h3 className="text-lg font-semibold">Delete Video?</h3>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-300 mb-2">
              Delete "{video.story?.title || "Untitled Video"}"?
            </p>
            <p className="text-sm text-red-600 dark:text-red-400 mb-4 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg">
              This will permanently delete the video file, thumbnail, and all
              temporary files from disk. This action cannot be undone.
            </p>
            <div className="flex items-center justify-end gap-3">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="cursor-pointer btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={isDeleting}
                className="cursor-pointer px-4 py-2 bg-red-500 text-white rounded-lg font-medium flex items-center gap-2 hover:bg-red-600 disabled:opacity-50"
              >
                {isDeleting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Trash2 className="w-4 h-4" />
                )}
                Delete Permanently
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
