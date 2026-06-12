import { Film, CheckCircle, XCircle, Loader2, AlertTriangle } from "lucide-react";
import { useFfmpegStatus } from "@/hooks/useFfmpegStatus";
import { StatusBadge } from "@/components/common/StatusBadge";

export function FfmpegStatus() {
  const { status, isLoading } = useFfmpegStatus();

  if (isLoading && !status) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Loader2 className="w-4 h-4 animate-spin" />
        Checking FFmpeg...
      </div>
    );
  }

  if (!status) return null;

  const showPathWarning =
    status.ffmpeg_installed && status.ffprobe_installed && !status.ffmpeg_in_path;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-3 flex-wrap">
        <StatusBadge
          label={status.ffmpeg_installed ? "FFmpeg OK" : "FFmpeg Missing"}
          icon={status.ffmpeg_installed ? CheckCircle : XCircle}
          variant={status.ffmpeg_installed ? "success" : "error"}
        />
        <StatusBadge
          label={status.ffprobe_installed ? "FFprobe OK" : "FFprobe Missing"}
          icon={status.ffprobe_installed ? CheckCircle : XCircle}
          variant={status.ffprobe_installed ? "success" : "error"}
        />
        {status.ffmpeg_installed && status.ffprobe_installed && (
          <StatusBadge
            label={status.ffmpeg_in_path ? "On PATH" : "Not on PATH"}
            icon={status.ffmpeg_in_path ? CheckCircle : AlertTriangle}
            variant={status.ffmpeg_in_path ? "success" : "warning"}
          />
        )}
        {status.can_generate_videos && status.ffmpeg_in_path && (
          <StatusBadge
            label="Ready"
            icon={Film}
            variant="success"
          />
        )}
      </div>
      {showPathWarning && (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          FFmpeg is installed but not on PATH. Restart the app or open Settings to refresh.
        </p>
      )}
    </div>
  );
}
