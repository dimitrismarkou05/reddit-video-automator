import {
  CheckCircle,
  CircleDot,
  Loader2,
  MinusCircle,
  Pause,
  XCircle,
  Youtube,
} from "lucide-react";
import {
  ACTIVE_GENERATION_STATUSES,
  STATUS_CONFIG,
  YT_STATUS_CONFIG,
  getVideoDisplayKey,
  getVideoStatusLabel,
  type StoryStatusVariant,
} from "@/config/videoStatus";
import type { GeneratedVideo } from "@/types";

const pillBase =
  "inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium leading-none shrink-0";

function getStatusIcon(statusKey: string) {
  switch (statusKey) {
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

function isSpinningIcon(statusKey: string, videoStatus: string): boolean {
  if (["done", "failed", "cancelled", "paused", "queued"].includes(statusKey)) {
    return false;
  }
  return ACTIVE_GENERATION_STATUSES.includes(videoStatus) || statusKey !== videoStatus;
}

interface VideoStatusBadgeProps {
  video?: Pick<
    GeneratedVideo,
    "status" | "current_step" | "progress_percent" | "queue_position" | "is_paused"
  > | null;
  displayKey?: string;
  label?: string;
  variant?: StoryStatusVariant;
  showPercent?: boolean;
  className?: string;
}

const variantToClasses: Record<StoryStatusVariant, string> = {
  primary: "bg-primary/10 text-primary",
  success: "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400",
  warning: "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400",
  error: "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400",
  info: "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400",
  neutral: "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400",
};

export function VideoStatusBadge({
  video,
  displayKey,
  label,
  variant,
  showPercent = false,
  className = "",
}: VideoStatusBadgeProps) {
  const key = displayKey ?? (video ? getVideoDisplayKey(video) : "processing");
  const config = STATUS_CONFIG[key] || STATUS_CONFIG.processing;
  const StatusIcon = getStatusIcon(key);
  const videoStatus = video?.status ?? key;
  const spinning = isSpinningIcon(key, videoStatus);

  const displayLabel =
    label ?? (video ? getVideoStatusLabel(video, { showPercent }) : config.label);

  const badgeClasses = variant
    ? variantToClasses[variant]
    : `${config.bgColor} ${config.color}`;

  return (
    <span
      className={`${pillBase} rounded-full ${badgeClasses} ${className}`}
    >
      <StatusIcon className={`w-3 h-3 ${spinning ? "animate-spin" : ""}`} />
      {displayLabel}
    </span>
  );
}

export function FormatBadge({ format }: { format: string }) {
  const label = format === "shorts" ? "9:16 Shorts" : "16:9 Normal";
  return (
    <span
      className={`${pillBase} rounded-full bg-neutral-100 dark:bg-neutral-700/70 text-neutral-700 dark:text-neutral-200`}
    >
      {label}
    </span>
  );
}

const YT_SHELL =
  "rounded-full bg-neutral-100 dark:bg-neutral-700/70 ring-1 ring-inset ring-red-200/50 dark:ring-red-400/15";

const YT_BADGE_TEXT: Record<string, string> = {
  not_uploaded: "text-neutral-700 dark:text-neutral-200",
  uploading: "text-neutral-700 dark:text-neutral-200",
  uploaded: "text-green-700 dark:text-green-300",
  failed: "text-red-700 dark:text-red-300",
  private: "text-amber-800 dark:text-amber-200",
  public: "text-green-700 dark:text-green-300",
  unlisted: "text-violet-700 dark:text-violet-300",
};

export function YouTubeStatusBadge({
  status,
  className = "",
}: {
  status: string;
  className?: string;
}) {
  const config = YT_STATUS_CONFIG[status] || YT_STATUS_CONFIG.not_uploaded;
  const textClass = YT_BADGE_TEXT[status] || YT_BADGE_TEXT.not_uploaded;
  const isUploading = status === "uploading";

  return (
    <span
      className={`${pillBase} ${YT_SHELL} ${className}`}
      title="YouTube upload status"
    >
      {isUploading ? (
        <Loader2 className="w-3 h-3 text-red-500/80 dark:text-red-400/90 animate-spin" />
      ) : (
        <Youtube className="w-3 h-3 text-red-500/80 dark:text-red-400/90" />
      )}
      <span className={textClass}>{config.label}</span>
    </span>
  );
}
