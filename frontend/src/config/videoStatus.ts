import {
  Film,
  CheckCircle,
  XCircle,
  Upload,
  Globe,
  AlertCircle,
  LucideIcon,
} from "lucide-react";

export interface StatusConfig {
  icon: LucideIcon;
  color: string;
  bg: string;
  label: string;
}

export const STATUS_CONFIG: Record<string, StatusConfig> = {
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

export const YT_STATUS_CONFIG: Record<
  string,
  { color: string; label: string }
> = {
  not_uploaded: { color: "text-gray-400", label: "Not Uploaded" },
  uploading: { color: "text-yellow-500", label: "Uploading..." },
  uploaded: { color: "text-green-500", label: "Live on YouTube" },
  upload_failed: { color: "text-red-500", label: "Upload Failed" },
};
