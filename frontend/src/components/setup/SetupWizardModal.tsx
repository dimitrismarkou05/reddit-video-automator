import { useEffect, useState, useRef } from "react";
import {
  Download,
  CheckCircle,
  AlertTriangle,
  RotateCcw,
  Mic,
  Film,
  ArrowRight,
} from "lucide-react";
import { ModalShell } from "@/components/common/ModalShell";
import { ProgressBar } from "@/components/common/ProgressBar";
import { ffmpegApi } from "@/services/api";
import { useFfmpegStatus } from "@/hooks/useFfmpegStatus";
import { useTtsLocalStatus } from "@/hooks/useTtsLocalStatus";
import { TtsInstallModal } from "@/components/tts/TtsInstallModal";
import toast from "react-hot-toast";

interface SetupWizardModalProps {
  onComplete: () => void;
}

export function SetupWizardModal({ onComplete }: SetupWizardModalProps) {
  const [step, setStep] = useState<1 | 2>(1);
  const [ffmpegInstalling, setFfmpegInstalling] = useState(false);
  const [ffmpegProgress, setFfmpegProgress] = useState(0);
  const [ffmpegStep, setFfmpegStep] = useState("");
  const [ffmpegError, setFfmpegError] = useState<string | null>(null);
  const [ffmpegComplete, setFfmpegComplete] = useState(false);

  const [ttsComplete, setTtsComplete] = useState(false);
  const [showTtsInstallModal, setShowTtsInstallModal] = useState(false);

  const { status: ffmpegStatus, refetch: refetchFfmpeg } = useFfmpegStatus();
  const { status: ttsStatus, refetch: refetchTts } = useTtsLocalStatus();

  const ffmpegEsRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (ffmpegStatus?.can_generate_videos && step === 1) {
      setFfmpegComplete(true);
      setStep(2);
    }
  }, [ffmpegStatus, step]);

  useEffect(() => {
    if (ffmpegComplete && ttsComplete) {
      onComplete();
    }
  }, [ffmpegComplete, ttsComplete, onComplete]);

  useEffect(() => {
    if (ffmpegStatus?.can_generate_videos) {
      setFfmpegComplete(true);
    }
  }, [ffmpegStatus]);

  useEffect(() => {
    if (ttsStatus?.installed) {
      setTtsComplete(true);
    }
  }, [ttsStatus]);

  useEffect(() => {
    return () => {
      ffmpegEsRef.current?.close();
    };
  }, []);

  const connectFfmpegSSE = () => {
    const baseUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
    const es = new EventSource(`${baseUrl}/api/v1/sse/ffmpeg/install-progress`);
    ffmpegEsRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (!data?.event_type) return;

        setFfmpegProgress(data.progress_percent || 0);
        setFfmpegStep(data.step || "");

        if (data.event_type === "complete") {
          setFfmpegComplete(true);
          setFfmpegInstalling(false);
          refetchFfmpeg();
          toast.success("FFmpeg installed successfully!");
          es.close();
        } else if (data.event_type === "failed") {
          setFfmpegError(data.error || "FFmpeg installation failed");
          setFfmpegInstalling(false);
          toast.error(data.error || "FFmpeg installation failed");
          es.close();
        } else if (data.event_type === "cancelled") {
          setFfmpegInstalling(false);
          toast("FFmpeg installation cancelled", { icon: "⚠️" });
          es.close();
        }
      } catch (e) {
        console.error("FFmpeg SSE parse error:", e);
      }
    };

    es.onerror = () => {
      es.close();
    };
  };

  const startFfmpegInstall = async () => {
    setFfmpegInstalling(true);
    setFfmpegError(null);
    setFfmpegComplete(false);
    connectFfmpegSSE();
    try {
      await ffmpegApi.install();
    } catch (e: any) {
      setFfmpegInstalling(false);
      setFfmpegError(
        e?.response?.data?.detail || "Failed to start FFmpeg installation",
      );
      toast.error(
        e?.response?.data?.detail || "Failed to start FFmpeg installation",
      );
    }
  };

  const retryFfmpeg = async () => {
    setFfmpegError(null);
    setFfmpegInstalling(true);
    connectFfmpegSSE();
    try {
      await ffmpegApi.retry();
    } catch (e: any) {
      setFfmpegInstalling(false);
      setFfmpegError(e?.response?.data?.detail || "Retry failed");
    }
  };

  return (
    <ModalShell onClose={() => {}} maxWidth="max-w-lg">
      <div className="p-6 space-y-6">
        <div className="text-center">
          <h2 className="text-xl font-bold">
            Welcome to Reddit Video Automator
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Let&apos;s set up the required components for video generation.
          </p>
        </div>

        <div className="flex items-center gap-2 mb-4">
          <div
            className={`flex-1 h-2 rounded-full ${step === 1 ? "bg-primary" : ffmpegComplete ? "bg-green-500" : "bg-gray-200 dark:bg-gray-700"}`}
          />
          <div
            className={`flex-1 h-2 rounded-full ${step === 2 ? "bg-primary" : ttsComplete ? "bg-green-500" : "bg-gray-200 dark:bg-gray-700"}`}
          />
        </div>

        {step === 1 && (
          <div className="space-y-4">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
                <Film className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h3 className="font-semibold">Step 1: Install FFmpeg</h3>
                <p className="text-xs text-gray-500">
                  Required for video rendering
                </p>
              </div>
            </div>

            {ffmpegComplete ? (
              <div className="flex items-center gap-2 text-green-600 bg-green-50 dark:bg-green-900/20 p-3 rounded-lg">
                <CheckCircle className="w-5 h-5" />
                <span className="text-sm font-medium">FFmpeg is ready</span>
              </div>
            ) : ffmpegInstalling ? (
              <div className="space-y-3">
                <ProgressBar progress={ffmpegProgress} size="lg" />
                <p className="text-sm text-gray-500 text-center">
                  {ffmpegStep}
                </p>
              </div>
            ) : ffmpegError ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-red-600 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg">
                  <AlertTriangle className="w-5 h-5" />
                  <span className="text-sm font-medium">{ffmpegError}</span>
                </div>
                <button
                  onClick={retryFfmpeg}
                  className="cursor-pointer w-full btn-primary flex items-center justify-center gap-2"
                >
                  <RotateCcw className="w-4 h-4" />
                  Retry FFmpeg Install
                </button>
              </div>
            ) : (
              <button
                onClick={startFfmpegInstall}
                className="cursor-pointer w-full btn-primary flex items-center justify-center gap-2"
              >
                <Download className="w-4 h-4" />
                Install FFmpeg
              </button>
            )}

            {ffmpegComplete && (
              <button
                onClick={() => setStep(2)}
                className="cursor-pointer w-full btn-secondary flex items-center justify-center gap-2"
              >
                Continue to Step 2
                <ArrowRight className="w-4 h-4" />
              </button>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
                <Mic className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h3 className="font-semibold">Step 2: Install TTS Model</h3>
                <p className="text-xs text-gray-500">
                  Required for voice narration
                </p>
              </div>
            </div>

            {ttsComplete ? (
              <div className="flex items-center gap-2 text-green-600 bg-green-50 dark:bg-green-900/20 p-3 rounded-lg">
                <CheckCircle className="w-5 h-5" />
                <span className="text-sm font-medium">TTS model is ready</span>
              </div>
            ) : (
              <button
                onClick={() => setShowTtsInstallModal(true)}
                className="cursor-pointer w-full btn-primary flex items-center justify-center gap-2"
              >
                <Download className="w-4 h-4" />
                Install TTS Model
              </button>
            )}

            {ttsComplete && (
              <button
                onClick={onComplete}
                className="cursor-pointer w-full btn-primary flex items-center justify-center gap-2"
              >
                <CheckCircle className="w-4 h-4" />
                Finish Setup
              </button>
            )}
          </div>
        )}
      </div>

      {showTtsInstallModal && (
        <TtsInstallModal
          onClose={() => {
            setShowTtsInstallModal(false);
            refetchTts().then((result: any) => {
              if (result?.data?.installed) {
                setTtsComplete(true);
              }
            });
          }}
        />
      )}
    </ModalShell>
  );
}
