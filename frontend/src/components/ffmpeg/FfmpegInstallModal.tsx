import { useEffect, useState, useRef, useCallback } from "react";
import { Download, AlertTriangle, RotateCcw, CheckCircle } from "lucide-react";
import { ModalShell } from "@/components/common/ModalShell";
import { ModalHeader } from "@/components/common/ModalHeader";
import { ProgressBar } from "@/components/common/ProgressBar";
import { LoadingSpinner } from "@/components/common/LoadingSpinner";
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
  const [isCancelling, setIsCancelling] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const installStartedRef = useRef(false);

  // Keep a live reference to store actions so the SSE handler never goes stale
  const storeRef = useRef({
    updateProgress,
    finishInstall,
    failInstall,
    resetInstall,
  });
  useEffect(() => {
    storeRef.current = {
      updateProgress,
      finishInstall,
      failInstall,
      resetInstall,
    };
  });

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, []);

  // SSE Connection - ONLY reconnect when isInstalling / isCancelling toggles
  useEffect(() => {
    if (!isInstalling && !isCancelling) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      return;
    }

    const baseUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
    const es = new EventSource(`${baseUrl}/api/v1/sse/ffmpeg/install-progress`);
    eventSourceRef.current = es;

    es.onopen = () => {
      console.log("[FFmpeg SSE] Connected");
    };

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log("[FFmpeg SSE] message:", data);
        if (!data || !data.event_type) return;

        const store = storeRef.current;

        switch (data.event_type) {
          case "mirror_switch":
            store.updateProgress(
              Number(data.progress_percent) || 0,
              data.step || "",
              data.mirror,
              0,
            );
            break;
          case "retry":
            store.updateProgress(
              Number(data.progress_percent) || 0,
              data.step || "",
              data.mirror,
              Number(data.retry_count) || 0,
            );
            break;
          case "download_progress":
            store.updateProgress(
              Number(data.progress_percent) || 0,
              data.step || "",
              data.mirror,
              Number(data.retry_count) || 0,
            );
            break;
          case "extracting":
            store.updateProgress(
              Number(data.progress_percent) || 65,
              data.step || "Extracting...",
              data.mirror,
              Number(data.retry_count) || 0,
            );
            break;
          case "installing":
            store.updateProgress(
              Number(data.progress_percent) || 85,
              data.step || "Installing...",
              data.mirror,
              Number(data.retry_count) || 0,
            );
            break;
          case "complete":
            store.updateProgress(100, "Installation complete!", data.mirror, 0);
            setIsComplete(true);
            refetch().then((result: any) => {
              if (result?.data) store.finishInstall(result.data);
            });
            toast.success("FFmpeg installed successfully!");
            es.close();
            break;
          case "failed":
            store.failInstall(data.error || "Installation failed");
            toast.error(data.error || "FFmpeg installation failed");
            es.close();
            break;
          case "cancelled":
            store.resetInstall();
            setIsCancelling(false);
            toast("FFmpeg installation cancelled", { icon: "⚠️" });
            es.close();
            break;
          case "idle":
            // ignore keep-alive / initial state
            break;
        }
      } catch (e) {
        console.error("[FFmpeg SSE] Parse error:", e);
      }
    };

    es.onerror = (err) => {
      console.warn("[FFmpeg SSE] Error:", err);
      // Only auto-close if we're done; otherwise let browser retry naturally
      if (isComplete || installError) {
        es.close();
      }
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isInstalling, isCancelling]);

  const handleStartInstall = async () => {
    if (installStartedRef.current || isStarting) return;
    installStartedRef.current = true;
    setIsStarting(true);
    setIsComplete(false);

    try {
      startInstall();
      await ffmpegApi.install();
      toast.success("Installation started");
    } catch (e: any) {
      installStartedRef.current = false;
      const msg =
        e?.response?.data?.detail ||
        e?.message ||
        "Failed to start installation";
      failInstall(msg);
      toast.error(msg);
    } finally {
      setIsStarting(false);
    }
  };

  const handleRetry = async () => {
    if (installStartedRef.current || isStarting) return;
    installStartedRef.current = true;
    setIsStarting(true);
    setIsComplete(false);
    resetInstall();

    try {
      startInstall();
      await ffmpegApi.retry();
      toast.success("Retrying installation...");
    } catch (e: any) {
      installStartedRef.current = false;
      const msg = e?.response?.data?.detail || e?.message || "Retry failed";
      failInstall(msg);
      toast.error(msg);
    } finally {
      setIsStarting(false);
    }
  };

  const handleCancel = async () => {
    if (isCancelling) return;
    setIsCancelling(true);

    try {
      await ffmpegApi.cancel();
    } catch (e) {
      // Ignore errors on cancel
    }

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    // Allow backend a moment to process cancellation and emit state
    setTimeout(() => {
      resetInstall();
      setIsCancelling(false);
      setShowCancelConfirm(false);
      onClose();
    }, 800);
  };

  const handleClose = useCallback(() => {
    if ((isInstalling || isCancelling) && !isComplete) {
      setShowCancelConfirm(true);
      return;
    }
    onClose();
  }, [isInstalling, isCancelling, isComplete, onClose]);

  // Reset installStartedRef when not installing
  useEffect(() => {
    if (!isInstalling && !isStarting) {
      installStartedRef.current = false;
    }
  }, [isInstalling, isStarting]);

  return (
    <ModalShell onClose={handleClose} maxWidth="max-w-lg">
      <ModalHeader
        title="FFmpeg Installation"
        subtitle="Required for video generation"
        icon={Download}
        onClose={handleClose}
        disabled={isInstalling && !isComplete}
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
                disabled={isCancelling}
              >
                Continue Installation
              </button>
              <button
                onClick={handleCancel}
                disabled={isCancelling}
                className="cursor-pointer px-3 py-1.5 bg-red-500 text-white rounded-lg text-sm font-medium hover:bg-red-600 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {isCancelling ? (
                  <>
                    <LoadingSpinner size="sm" className="border-orange-500" />
                    <span>Cancelling...</span>
                  </>
                ) : (
                  "Cancel Installation"
                )}
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
              disabled={isStarting}
              className="cursor-pointer btn-primary flex items-center gap-2 mx-auto disabled:opacity-50"
            >
              {isStarting ? (
                <>
                  <LoadingSpinner size="sm" />
                  <span>Starting...</span>
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" />
                  Install FFmpeg Now
                </>
              )}
            </button>
          </div>
        )}

        {isInstalling && !isComplete && (
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
              disabled={isCancelling}
              className="cursor-pointer w-full btn-secondary text-sm disabled:opacity-50"
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
                disabled={isStarting}
                className="cursor-pointer flex-1 btn-primary flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {isStarting ? (
                  <>
                    <LoadingSpinner size="sm" />
                    <span>Retrying...</span>
                  </>
                ) : (
                  <>
                    <RotateCcw className="w-4 h-4" />
                    Retry
                  </>
                )}
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

        {isComplete && (
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
