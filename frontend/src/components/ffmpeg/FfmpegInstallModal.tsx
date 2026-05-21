import { useEffect, useState, useRef } from "react";
import { Download, AlertTriangle, RotateCcw, CheckCircle } from "lucide-react";
import { ModalShell } from "@/components/common/ModalShell";
import { ModalHeader } from "@/components/common/ModalHeader";
import { ProgressBar } from "@/components/common/ProgressBar";
import { useFfmpegStore } from "@/store/ffmpeg";
import { ffmpegApi } from "@/services/api";
import { useFfmpegStatus } from "@/hooks/useFfmpegStatus";
import toast from "react-hot-toast";

interface FfmpegInstallModalProps {
  onClose: () => void;
}

export function FfmpegInstallModal({ onClose }: FfmpegInstallModalProps) {
  const {
    isInstalling,
    installProgress,
    installStep,
    currentMirror,
    retryCount,
    installError,
    startInstall,
    updateProgress,
    finishInstall,
    failInstall,
    resetInstall,
  } = useFfmpegStore();

  const { refetch } = useFfmpegStatus();
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    // Only connect SSE when installation is active
    if (!isInstalling) return;

    const es = new EventSource(
      `${import.meta.env.VITE_API_URL || "http://localhost:8000"}/sse/ffmpeg/install-progress`,
    );
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (!data.event_type) return;

        switch (data.event_type) {
          case "mirror_switch":
            updateProgress(
              data.progress_percent || 0,
              data.step,
              data.mirror,
              0,
            );
            break;
          case "retry":
            updateProgress(
              data.progress_percent || 0,
              data.step,
              data.mirror,
              data.retry_count,
            );
            break;
          case "download_progress":
            updateProgress(
              data.progress_percent || 0,
              data.step,
              data.mirror,
              data.retry_count,
            );
            break;
          case "extracting":
            updateProgress(55, data.step, data.mirror, data.retry_count);
            break;
          case "installing":
            updateProgress(85, data.step, data.mirror, data.retry_count);
            break;
          case "complete":
            updateProgress(
              100,
              "Installation complete!",
              data.mirror,
              data.retry_count,
            );
            setIsComplete(true);
            refetch().then((result) => {
              if (result.data) finishInstall(result.data);
            });
            toast.success("FFmpeg installed successfully!");
            es.close();
            break;
          case "failed":
            failInstall(data.error || "Installation failed");
            toast.error(data.error || "FFmpeg installation failed");
            es.close();
            break;
          case "cancelled":
            resetInstall();
            toast("FFmpeg installation cancelled", { icon: "⚠️" });
            es.close();
            break;
        }
      } catch (e) {
        console.error("SSE parse error:", e);
      }
    };

    es.onerror = () => {
      // Auto-reconnect handled by browser, but close on terminal states
      if (isComplete || installError) {
        es.close();
      }
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [isInstalling]); // Only re-run when installation starts/stops

  const handleStartInstall = async () => {
    try {
      startInstall();
      await ffmpegApi.install();
      toast.success("Installation started");
    } catch (e: any) {
      failInstall(e?.response?.data?.detail || "Failed to start installation");
      toast.error("Failed to start FFmpeg installation");
    }
  };

  const handleRetry = async () => {
    resetInstall();
    setIsComplete(false);
    try {
      startInstall();
      await ffmpegApi.retry();
      toast.success("Retrying installation...");
    } catch (e: any) {
      failInstall(e?.response?.data?.detail || "Retry failed");
      toast.error("Failed to retry installation");
    }
  };

  const handleCancel = async () => {
    if (isInstalling && !showCancelConfirm) {
      setShowCancelConfirm(true);
      return;
    }

    try {
      await ffmpegApi.cancel();
    } catch (e) {
      // Ignore errors on cancel
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
    resetInstall();
    setShowCancelConfirm(false);
    onClose();
  };

  const handleClose = () => {
    if (isInstalling) {
      setShowCancelConfirm(true);
      return;
    }
    onClose();
  };

  return (
    <ModalShell onClose={handleClose} maxWidth="max-w-lg">
      <ModalHeader
        title="FFmpeg Installation"
        subtitle="Required for video generation"
        icon={Download}
        onClose={handleClose}
        disabled={isInstalling}
      />

      <div className="p-6 space-y-5">
        {showCancelConfirm && (
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4 space-y-3">
            <div className="flex items-center gap-2 text-yellow-700 dark:text-yellow-400">
              <AlertTriangle className="w-5 h-5" />
              <span className="font-medium">Installation in progress</span>
            </div>
            <p className="text-sm text-yellow-600 dark:text-yellow-300">
              Cancel anyway? Video generation will remain disabled.
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setShowCancelConfirm(false)}
                className="cursor-pointer btn-secondary text-sm"
              >
                Continue Installation
              </button>
              <button
                onClick={handleCancel}
                className="cursor-pointer px-3 py-1.5 bg-red-500 text-white rounded-lg text-sm font-medium hover:bg-red-600"
              >
                Cancel Installation
              </button>
            </div>
          </div>
        )}

        {!isInstalling && !installError && !isComplete && (
          <div className="text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto">
              <Download className="w-8 h-8 text-primary" />
            </div>
            <div>
              <h3 className="text-lg font-semibold">FFmpeg Not Installed</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                FFmpeg is required to generate videos from Reddit stories. The
                installer will download and set it up automatically.
              </p>
            </div>
            <button
              onClick={handleStartInstall}
              className="cursor-pointer btn-primary flex items-center gap-2 mx-auto"
            >
              <Download className="w-4 h-4" />
              Install FFmpeg Now
            </button>
          </div>
        )}

        {isInstalling && (
          <div className="space-y-4">
            <div className="text-center">
              <div className="relative w-16 h-16 mx-auto mb-4">
                <div className="absolute inset-0 rounded-full border-4 border-primary/20" />
                <div className="absolute inset-0 rounded-full border-4 border-primary border-t-transparent animate-spin" />
                <Download className="absolute inset-0 m-auto w-6 h-6 text-primary" />
              </div>
              <h3 className="text-lg font-semibold">Installing FFmpeg...</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {installStep}
              </p>
            </div>

            <ProgressBar progress={installProgress} size="lg" />

            {currentMirror && (
              <p className="text-xs text-gray-500 dark:text-gray-400 text-center truncate">
                Mirror: {currentMirror}
              </p>
            )}

            {retryCount > 0 && (
              <p className="text-xs text-yellow-600 dark:text-yellow-400 text-center">
                Retry {retryCount}/3
              </p>
            )}

            <button
              onClick={() => setShowCancelConfirm(true)}
              className="cursor-pointer w-full btn-secondary text-sm"
            >
              Cancel
            </button>
          </div>
        )}

        {installError && !isInstalling && (
          <div className="space-y-4">
            <div className="text-center">
              <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center mx-auto mb-4">
                <AlertTriangle className="w-8 h-8 text-red-500" />
              </div>
              <h3 className="text-lg font-semibold text-red-600 dark:text-red-400">
                Installation Failed
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {installError}
              </p>
            </div>

            <div className="flex gap-2">
              <button
                onClick={handleRetry}
                className="cursor-pointer flex-1 btn-primary flex items-center justify-center gap-2"
              >
                <RotateCcw className="w-4 h-4" />
                Retry
              </button>
              <button
                onClick={onClose}
                className="cursor-pointer flex-1 btn-secondary"
              >
                Close
              </button>
            </div>
          </div>
        )}

        {isComplete && !isInstalling && (
          <div className="text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center mx-auto">
              <CheckCircle className="w-8 h-8 text-green-500" />
            </div>
            <h3 className="text-lg font-semibold text-green-600 dark:text-green-400">
              Installation Complete!
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              FFmpeg is now ready. You can generate videos.
            </p>
            <button onClick={onClose} className="cursor-pointer btn-primary">
              Done
            </button>
          </div>
        )}
      </div>
    </ModalShell>
  );
}
