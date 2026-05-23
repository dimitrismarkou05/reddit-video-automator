import {
  Film,
  CheckCircle,
  XCircle,
  Upload,
  Globe,
  AlertCircle,
  Loader2,
  PauseCircle,
  Clock,
  LucideIcon,
} from "lucide-react";

export interface StatusConfig {
  icon: LucideIcon;
  color: string;
  bg: string;
  label: string;
}

export const STATUS_CONFIG: Record<string, StatusConfig> = {
  queued: {
    icon: Clock,
    color: "text-gray-500",
    bg: "bg-gray-100 dark:bg-gray-700",
    label: "Queued",
  },
  processing: {
    icon: Loader2,
    color: "text-blue-500",
    bg: "bg-blue-100 dark:bg-blue-900/30",
    label: "Processing",
  },
  tts_done: {
    icon: Loader2,
    color: "text-blue-500",
    bg: "bg-blue-100 dark:bg-blue-900/30",
    label: "TTS Done",
  },
  transcribe_done: {
    icon: Loader2,
    color: "text-blue-500",
    bg: "bg-blue-100 dark:bg-blue-900/30",
    label: "Transcribing",
  },
  subtitles_done: {
    icon: Loader2,
    color: "text-blue-500",
    bg: "bg-blue-100 dark:bg-blue-900/30",
    label: "Subtitles",
  },
  compositing_done: {
    icon: Loader2,
    color: "text-blue-500",
    bg: "bg-blue-100 dark:bg-blue-900/30",
    label: "Compositing",
  },
  paused: {
    icon: PauseCircle,
    color: "text-yellow-500",
    bg: "bg-yellow-100 dark:bg-yellow-900/30",
    label: "Paused",
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
  cancelled: {
    icon: XCircle,
    color: "text-gray-500",
    bg: "bg-gray-100 dark:bg-gray-700",
    label: "Cancelled",
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

export const YT_STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  not_uploaded: { color: "text-gray-400", label: "Not Uploaded" },
  uploading: { color: "text-yellow-500", label: "Uploading..." },
  uploaded: { color: "text-green-500", label: "Live on YouTube" },
  upload_failed: { color: "text-red-500", label: "Upload Failed" },
};

export const ACTIVE_GENERATION_STATUSES = [
  "queued",
  "processing",
  "tts_done",
  "transcribe_done",
  "subtitles_done",
  "compositing_done",
  "paused",
];

export const TERMINAL_STATUSES = ["done", "failed", "cancelled"];
