import { useState } from "react";
import { AlertTriangle, Download, Settings } from "lucide-react";
import { ModalShell } from "@/components/common/ModalShell";
import { FfmpegInstallModal } from "./FfmpegInstallModal";

interface FfmpegMissingModalProps {
  onClose: () => void;
  onSkip: () => void;
}

export function FfmpegMissingModal({
  onClose,
  onSkip,
}: FfmpegMissingModalProps) {
  const [showInstallModal, setShowInstallModal] = useState(false);

  if (showInstallModal) {
    return (
      <FfmpegInstallModal
        onClose={() => {
          setShowInstallModal(false);
          onClose();
        }}
      />
    );
  }

  return (
    <ModalShell onClose={onClose} maxWidth="max-w-md">
      <div className="p-6 space-y-5">
        <div className="text-center">
          <div className="w-14 h-14 rounded-full bg-yellow-100 dark:bg-yellow-900/30 flex items-center justify-center mx-auto mb-4">
            <AlertTriangle className="w-7 h-7 text-yellow-600 dark:text-yellow-400" />
          </div>
          <h3 className="text-lg font-semibold">FFmpeg Required</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
            FFmpeg is needed to generate videos from Reddit stories. It was not
            detected on your system.
          </p>
        </div>

        <div className="space-y-2 text-sm text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-surface-dark/50 rounded-lg p-3">
          <p>Without FFmpeg you can still:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Fetch and browse stories</li>
            <li>Manage subreddits</li>
            <li>Upload existing videos to YouTube</li>
          </ul>
        </div>

        <div className="flex flex-col gap-2">
          <button
            onClick={() => setShowInstallModal(true)}
            className="cursor-pointer btn-primary flex items-center justify-center gap-2"
          >
            <Download className="w-4 h-4" />
            Install Now
          </button>
          <button
            onClick={() => {
              onSkip();
              onClose();
            }}
            className="cursor-pointer btn-secondary flex items-center justify-center gap-2"
          >
            <Settings className="w-4 h-4" />
            Install Later
          </button>
        </div>
      </div>
    </ModalShell>
  );
}
