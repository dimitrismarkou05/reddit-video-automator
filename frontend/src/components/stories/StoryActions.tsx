import { Film, ExternalLink, Trash2 } from "lucide-react";

interface StoryActionsProps {
  hasVideo: boolean;
  permalink: string;
  onGenerate: () => void;
  onDelete: () => void;
}

export function StoryActions({
  hasVideo,
  permalink,
  onGenerate,
  onDelete,
}: StoryActionsProps) {
  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={onGenerate}
        disabled={hasVideo}
        className={`cursor-pointer p-2 rounded-lg transition-colors ${
          hasVideo
            ? "bg-green-100 dark:bg-green-900/30 text-green-600 cursor-default"
            : "bg-primary/10 text-primary hover:bg-primary/20"
        }`}
        title={hasVideo ? "Video ready" : "Generate video"}
      >
        <Film className="w-5 h-5" />
      </button>
      <a
        href={permalink}
        target="_blank"
        rel="noopener noreferrer"
        className="p-2 rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
        title="View on Reddit"
      >
        <ExternalLink className="w-5 h-5" />
      </a>
      <button
        onClick={onDelete}
        className="cursor-pointer p-2 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
        title="Delete"
      >
        <Trash2 className="w-5 h-5" />
      </button>
    </div>
  );
}
