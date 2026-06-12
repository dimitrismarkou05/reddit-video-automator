import { Film, ExternalLink, Trash2, Loader2, Loader, Upload } from "lucide-react";
import toast from "react-hot-toast";
import type { GeneratedVideo } from "@/types";

interface StoryActionsProps {
  hasVideo: boolean;
  generatedVideo?: GeneratedVideo | null;
  permalink: string;
  onGenerate: () => void;
  onUpload?: () => void;
  onDelete: () => void;
  canGenerate?: boolean;
  isDetectingFfmpeg?: boolean;
  isGenerating?: boolean;
}

export function StoryActions({
  generatedVideo,
  permalink,
  onGenerate,
  onUpload,
  onDelete,
  canGenerate = true,
  isDetectingFfmpeg = false,
  isGenerating = false,
}: StoryActionsProps) {
  const canUpload =
    generatedVideo?.status === "done" &&
    generatedVideo.youtube_upload_status === "not_uploaded";
  const isUploaded =
    generatedVideo?.status === "done" &&
    generatedVideo.youtube_upload_status === "uploaded" &&
    !!generatedVideo.youtube_video_id;

  const handleGenerateClick = () => {
    if (isDetectingFfmpeg) return;
    if (!canGenerate) {
      toast.error("FFmpeg not installed. Please install FFmpeg in Settings to generate videos.");
      return;
    }
    onGenerate();
  };

  const handleUploadClick = () => {
    onUpload?.();
  };

  return (
    <div className="flex flex-col gap-2">
      {canUpload ? (
        <button
          onClick={handleUploadClick}
          className="p-2 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 cursor-pointer"
          title="Upload to YouTube"
        >
          <Upload className="w-5 h-5" />
        </button>
      ) : isUploaded ? (
        <a
          href={`https://youtube.com/watch?v=${generatedVideo!.youtube_video_id}`}
          target="_blank"
          rel="noopener noreferrer"
          className="p-2 rounded-lg bg-green-100 dark:bg-green-900/30 text-green-600 hover:bg-green-200 dark:hover:bg-green-900/40"
          title="View on YouTube"
        >
          <ExternalLink className="w-5 h-5" />
        </a>
      ) : (
        <button
          onClick={handleGenerateClick}
          disabled={isDetectingFfmpeg || (!canGenerate && !isGenerating)}
          className={`p-2 rounded-lg  ${
            isGenerating
              ? "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-600 cursor-pointer animate-pulse"
              : isDetectingFfmpeg
                ? "bg-gray-100 dark:bg-surface-dark dark:border dark:border-border-dark text-gray-400 cursor-wait"
                : canGenerate
                  ? "bg-primary/10 text-primary hover:bg-primary/20 cursor-pointer"
                  : "bg-gray-100 dark:bg-surface-dark dark:border dark:border-border-dark text-gray-400 cursor-not-allowed"
          }`}
          title={
            isGenerating
              ? "Generation in progress..."
              : isDetectingFfmpeg
                ? "Searching for FFmpeg..."
                : canGenerate
                  ? "Generate video"
                  : "FFmpeg not installed"
          }
        >
          {isDetectingFfmpeg ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : isGenerating ? (
            <Loader className="w-5 h-5 animate-spin" />
          ) : (
            <Film className="w-5 h-5" />
          )}
        </button>
      )}
      <a
        href={permalink}
        target="_blank"
        rel="noopener noreferrer"
        className="p-2 rounded-lg bg-gray-100 dark:bg-surface-dark dark:border dark:border-border-dark text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-white/5"
        title="View on Reddit"
      >
        <ExternalLink className="w-5 h-5" />
      </a>
      <button
        onClick={onDelete}
        className="cursor-pointer p-2 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/35 "
        title="Delete"
      >
        <Trash2 className="w-5 h-5" />
      </button>
    </div>
  );
}
