import { Film, CheckCircle, XCircle, Loader2 } from "lucide-react";
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

  return (
    <div className="flex items-center gap-3">
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
      {status.can_generate_videos && (
        <StatusBadge
          label="Ready"
          icon={Film}
          variant="success"
        />
      )}
    </div>
  );
}
