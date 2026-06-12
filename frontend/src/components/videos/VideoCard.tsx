import { useState, useEffect } from "react";
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
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import {
  ACTIVE_GENERATION_STATUSES,
  TERMINAL_VIDEO_STATUSES,
  truncateTitle,
  isVideoGenerating,
} from "@/config/videoStatus";
import { useLiveGeneratedVideo } from "@/hooks/useLiveGeneratedVideo";
import {
  FormatBadge,
  VideoStatusBadge,
  YouTubeStatusBadge,
} from "@/components/videos/VideoStatusBadge";
import { UploadModal } from "@/components/UploadModal";
import { StatsModal } from "@/components/StatsModal";
import { CancelConfirmModal } from "@/components/modals/CancelConfirmModal";
import { getVideoThumbnailUrl, videoApi } from "@/services/api";
import type { GeneratedVideo } from "@/types";
import toast from "react-hot-toast";
import { useQueryClient } from "@tanstack/react-query";
import { cleanupDeletedVideo, isVideoPaused, optimisticallyPauseVideo, optimisticallyResumeVideo } from "@/utils/videoQueries";

function getVideoTitle(video: GeneratedVideo): string {
  return video.story_title || video.story?.title || "Untitled Video";
}

interface VideoCardProps {
  video: GeneratedVideo;
}

export function VideoCard({ video }: VideoCardProps) {
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showStatsModal, setShowStatsModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [isPausing, setIsPausing] = useState(false);
  const [isResuming, setIsResuming] = useState(false);
  const [imgError, setImgError] = useState(false);
  const queryClient = useQueryClient();

  const displayTitle = truncateTitle(getVideoTitle(video));
  const fullTitle = getVideoTitle(video);
  const subreddit = video.story_subreddit || video.story?.subreddit;

  const isLive =
    isVideoGenerating(video) ||
    ACTIVE_GENERATION_STATUSES.includes(video.status) ||
    video.status === "paused";
  const liveVideo = useLiveGeneratedVideo(video, isLive);
  const displayVideo = liveVideo ?? video;

  const isPaused = isVideoPaused(displayVideo);
  const isGenerating =
    !isPaused &&
    (isVideoGenerating(displayVideo) ||
      ACTIVE_GENERATION_STATUSES.includes(displayVideo.status));
  const isTerminal = TERMINAL_VIDEO_STATUSES.includes(displayVideo.status);

  const thumbnailSrc =
    video.status === "done"
      ? getVideoThumbnailUrl(video.id, video.completed_at || video.id)
      : null;

  useEffect(() => {
    setImgError(false);
  }, [video.id, video.thumbnail_path, video.status]);

  const handlePause = async () => {
    if (isPausing) return;
    const rollback = optimisticallyPauseVideo(
      queryClient,
      displayVideo,
      video.story_id,
    );
    setIsPausing(true);
    try {
      await videoApi.pause(video.id);
      toast.success("Paused");
    } catch (e: any) {
      rollback();
      toast.error(e.response?.data?.detail || "Failed to pause");
    } finally {
      setIsPausing(false);
    }
  };

  const handleResume = async () => {
    if (isResuming) return;
    const rollback = optimisticallyResumeVideo(
      queryClient,
      displayVideo,
      video.story_id,
    );
    setIsResuming(true);
    try {
      await videoApi.resume(video.id);
      toast.success("Resuming...");
    } catch (e: any) {
      rollback();
      toast.error(e.response?.data?.detail || "Failed to resume");
    } finally {
      setIsResuming(false);
    }
  };

  const handleCancel = async () => {
    if (isCancelling) return;
    setShowCancelConfirm(false);
    setIsCancelling(true);
    try {
      await videoApi.cancel(video.id);
      cleanupDeletedVideo(queryClient, {
        videoId: video.id,
        storyId: video.story_id,
        storyStatus: "video_cancelled",
      });
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
      cleanupDeletedVideo(queryClient, {
        videoId: video.id,
        storyId: video.story_id,
        invalidateVideoList: true,
      });
      toast.success("Video deleted");
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to delete");
    } finally {
      setIsDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  return (
    <div className="card overflow-hidden">
      {/* Thumbnail */}
      <div className="relative aspect-video bg-neutral-900">
        {thumbnailSrc && !imgError ? (
          <img
            src={thumbnailSrc}
            alt={fullTitle}
            className="w-full h-full object-cover"
            onError={() => setImgError(true)}
          />
        ) : displayVideo.status === "failed" ? (
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
        ) : isPaused ? (
          <div className="w-full h-full flex flex-col items-center justify-center bg-yellow-900/10">
            <Pause className="w-10 h-10 text-yellow-500 mb-2" />
            <span className="text-xs text-yellow-500 font-medium">Paused</span>
          </div>
        ) : isGenerating ? (
          <div className="w-full h-full flex flex-col items-center justify-center">
            <Loader2 className="w-10 h-10 text-gray-500 animate-spin mb-2" />
            <span className="text-xs text-gray-500">Generating...</span>
          </div>
        ) : video.status === "done" ? (
          <div className="w-full h-full flex flex-col items-center justify-center">
            <Loader2 className="w-10 h-10 text-gray-500 animate-spin mb-2" />
            <span className="text-xs text-gray-500">Loading thumbnail...</span>
          </div>
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center">
            <Film className="w-10 h-10 text-gray-600 mb-2" />
            <span className="text-xs text-gray-500">
              {video.status === "cancelled" ? "Cancelled" : "No preview"}
            </span>
          </div>
        )}
        {(isGenerating || isPaused) && (
          <div className="absolute inset-x-0 bottom-0 h-1.5 bg-gray-200 dark:bg-gray-700 overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${
                isPaused ? "bg-yellow-500" : "bg-primary"
              }`}
              style={{ width: `${displayVideo.progress_percent}%` }}
            />
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-4">
        <h3
          className="font-semibold text-sm mb-1 truncate"
          title={fullTitle}
        >
          {displayTitle}
        </h3>

        {/* Subreddit badge */}
        {subreddit && (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary mb-2">
            r/{subreddit}
          </span>
        )}

        {/* Error display */}
        {displayVideo.status === "failed" && displayVideo.error_message && (
          <div className="mb-2 p-2 bg-red-50 dark:bg-red-900/20 rounded-lg">
            <p className="text-xs text-red-600 dark:text-red-400">
              {displayVideo.error_message}
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

        <div className="flex items-center gap-2 mb-3 w-full">
          <FormatBadge format={video.format} />
          <VideoStatusBadge video={displayVideo} showPercent={isGenerating} />
          <YouTubeStatusBadge
            status={video.youtube_upload_status}
            className="ml-auto"
          />
        </div>

        {video.youtube_video_id && (
          <p className="text-xs text-gray-400 font-mono mb-3">
            {video.youtube_video_id}
          </p>
        )}

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          {isGenerating && !isPaused && (
            <>
              <button
                onClick={handlePause}
                disabled={isPausing || isCancelling}
                className="cursor-pointer flex-1 btn-secondary text-xs py-2 flex items-center justify-center gap-1 disabled:opacity-50"
              >
                {isPausing ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Pause className="w-3 h-3" />
                )}
                {isPausing ? "Pausing..." : "Pause"}
              </button>
              <button
                onClick={() => setShowCancelConfirm(true)}
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

          {isPaused && (
            <>
              <button
                onClick={handleResume}
                disabled={isResuming || isCancelling}
                className="cursor-pointer flex-1 btn-primary text-xs py-2 flex items-center justify-center gap-1 disabled:opacity-50"
              >
                {isResuming ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Play className="w-3 h-3" />
                )}
                {isResuming ? "Resuming..." : "Resume"}
              </button>
              <button
                onClick={() => setShowCancelConfirm(true)}
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

      {showUploadModal && (
        <UploadModal video={video} onClose={() => setShowUploadModal(false)} />
      )}

      {showStatsModal && video.youtube_video_id && (
        <StatsModal
          videoId={video.youtube_video_id}
          onClose={() => setShowStatsModal(false)}
        />
      )}

      {showCancelConfirm && (
        <CancelConfirmModal
          videoTitle={fullTitle}
          onConfirm={handleCancel}
          onCancel={() => setShowCancelConfirm(false)}
          isConfirming={isCancelling}
        />
      )}

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
              Delete "{fullTitle}"?
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
