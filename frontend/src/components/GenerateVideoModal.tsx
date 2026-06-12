import { useState, useEffect, useCallback, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  X,
  Film,
  Mic,
  Type,
  Image,
  Settings,
  Pause,
  Play,
  Loader2,
  FolderOpen,
  FileVideo,
  CheckCircle,
  AlertTriangle,
  RotateCw,
  ListOrdered,
} from "lucide-react";
import { videoApi, ttsLocalApi, settingsApi, videoProgressSSE } from "@/services/api";
import type { Story, SubtitleStyle as SubtitleStyleType } from "@/types";
import { useVideoProgress } from "@/hooks/useVideoProgress";
import { useVideoJobsStore } from "@/store/videoJobs";
import { ACTIVE_GENERATION_STATUSES } from "@/config/videoStatus";
import {
  removeVideoFromCache,
  removeVideoQuery,
  clearStoryGeneratedVideo,
  storyQueryKey,
} from "@/utils/videoQueries";
import toast from "react-hot-toast";

const STEP_LABELS: Record<string, string> = {
  queued: "Waiting in queue...",
  preparing: "Preparing narrative...",
  downloading_model: "Downloading TTS model...",
  initializing_pipeline: "Initializing pipeline...",
  generating_script: "Generating script...",
  tts: "Generating speech (TTS)...",
  tts_synthesizing: "Synthesizing audio...",
  tts_done: "Speech synthesis complete",
  transcribing: "Transcribing audio...",
  transcribe_done: "Transcription complete",
  generating_subtitles: "Generating subtitles...",
  subtitles_done: "Subtitles generated",
  selecting_background: "Selecting background video...",
  compositing: "Compositing video with FFmpeg...",
  ffmpeg_processing: "FFmpeg processing...",
  compositing_done: "Video compositing complete",
  thumbnail: "Generating thumbnail...",
  generating_thumbnail: "Creating thumbnail...",
  uploading: "Uploading/exporting...",
  cleanup: "Finalizing and cleaning up...",
  done: "Complete!",
  failed: "Generation failed",
  cancelled: "Cancelled",
  paused: "Generation paused",
  processing: "Processing...",
};

// Active statuses where the ellipsis animation should run.
const ANIMATING_STATUSES = new Set([
  "preparing", "downloading_model", "tts", "tts_synthesizing",
  "transcribing", "generating_subtitles", "selecting_background",
  "compositing", "generating_thumbnail", "processing",
]);

interface GenerateVideoModalProps {
  story: Story;
  onClose: () => void;
  existingVideoId?: number | null;
  isUpdate?: boolean;
  parentStory?: Story | null;
}

export function GenerateVideoModal({
  story,
  onClose,
  existingVideoId,
  isUpdate = false,
  parentStory = null,
}: GenerateVideoModalProps) {
  const queryClient = useQueryClient();
  const { setActiveModal, registerJob, updateJob, removeJob, removeJobsForStory } =
    useVideoJobsStore();

  const [settings, setSettings] = useState({
    voice_id: "default",
    background_source: "",
    video_format: "shorts" as "shorts" | "normal",
    include_updates: true,
    subtitle_position: "center" as "center" | "bottom" | "top",
    subtitle_size: 48,
    generate_hashtags: true,
  });

  // FIX 12b: Background validation state
  const [bgValidation, setBgValidation] = useState<{
    valid: boolean | null;
    error: string | null;
    checking: boolean;
  }>({ valid: null, error: null, checking: false });

  // Check if story already has a generated video or is in progress
  const existingVideo = story.generated_video;
  const hasExistingVideo = !!existingVideo;
  const existingVideoIsActive =
    hasExistingVideo &&
    !["done", "failed", "cancelled"].includes(existingVideo.status);

  const [videoId, setVideoId] = useState<number | null>(
    existingVideoId ?? (existingVideo?.id || null),
  );
  const [lastError, setLastError] = useState<string | null>(null);
  const [hasStartedGeneration, setHasStartedGeneration] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelCompleted, setCancelCompleted] = useState(false);

  const cancelCompleteRef = useRef(false);
  const notifiedTerminalRef = useRef(false);

  // Set active modal in store for global tracking
  useEffect(() => {
    if (videoId) {
      setActiveModal(videoId, story.id);
    }
    return () => {
      const state = useVideoJobsStore.getState();
      if (state.activeModalVideoId === videoId) {
        setActiveModal(null, null);
      }
    };
  }, [videoId, story.id, setActiveModal]);

  const { data: voices } = useQuery({
    queryKey: ["tts-voices"],
    queryFn: async () => {
      const { data } = await ttsLocalApi.listVoices();
      return data as { id: string; name: string }[];
    },
    staleTime: 60000,
  });

  // Load default voice (use batchGet to avoid 404 on fresh installs).
  useEffect(() => {
    const loadDefault = async () => {
      try {
        const { data } = await settingsApi.batchGet(["default_tts_voice"]);
        const saved = data?.default_tts_voice;
        if (saved && saved !== "default") {
          setSettings((s) => ({ ...s, voice_id: saved }));
          return;
        }
      } catch (e) {
        console.debug("Failed to load default voice:", e);
      }
      if (voices && voices.length > 0) {
        const fallbackId = voices[0].id;
        setSettings((s) => ({ ...s, voice_id: fallbackId }));
        // Auto-persist so generation always has a valid voice without needing Save.
        try {
          await settingsApi.set("default_tts_voice", fallbackId);
        } catch {
          // non-critical
        }
      }
    };
    loadDefault();
  }, [voices]);

  // Track video progress via SSE
  const handleComplete = useCallback((data: any) => {
    if (data.status === "done" && !notifiedTerminalRef.current) {
      notifiedTerminalRef.current = true;
      toast.success("Video generation complete!");
    }
  }, []);

  const handleCancelComplete = useCallback(
    (id: number) => {
      videoProgressSSE.disconnect();
      setCancelCompleted(true);
      setIsCancelling(false);
      setVideoId(null);
      setHasStartedGeneration(false);
      setLastError(null);
      notifiedTerminalRef.current = true;

      if (!cancelCompleteRef.current) {
        cancelCompleteRef.current = true;
        removeVideoFromCache(queryClient, id);
        removeVideoQuery(queryClient, id);
        clearStoryGeneratedVideo(queryClient, story.id, {
          storyStatus: "video_cancelled",
        });
        removeJobsForStory(story.id);
        setActiveModal(null, null);
        toast("Generation cancelled", { icon: "⚠️" });
        queryClient.invalidateQueries({ queryKey: ["stories"] });
        queryClient.invalidateQueries({ queryKey: storyQueryKey(story.id) });
      }
    },
    [queryClient, removeJobsForStory, setActiveModal, story.id],
  );

  const handleError = useCallback(
    (data: any) => {
      if (data.status === "deleted" || data.status === "cancelled") {
        handleCancelComplete(data.video_id);
        return;
      }
      if (!notifiedTerminalRef.current) {
        notifiedTerminalRef.current = true;
        if (data.status === "failed") {
          toast.error(data.error_message || "Video generation failed");
        }
      }
    },
    [handleCancelComplete],
  );

  const { progress } = useVideoProgress({
    videoId,
    onComplete: handleComplete,
    onError: handleError,
  });

  // Derive UI state from progress
  const isGenerating =
    !cancelCompleted &&
    (progress
      ? ACTIVE_GENERATION_STATUSES.includes(progress.status)
      : hasStartedGeneration && existingVideoIsActive);

  const isPaused = progress?.status === "paused";
  const isFailed = progress?.status === "failed" || lastError !== null;
  const isDone =
    progress?.status === "done" ||
    (hasExistingVideo && existingVideo?.status === "done");
  const isCancelled = progress?.status === "cancelled";

  // Sync progress state with store
  useEffect(() => {
    if (!progress) return;

    if (
      (progress.status === "deleted" || progress.status === "cancelled") &&
      videoId
    ) {
      handleCancelComplete(videoId);
      return;
    }

    if (cancelCompleted || cancelCompleteRef.current) {
      return;
    }

    if (videoId) {
      updateJob(videoId, {
        status: progress.status,
        progress: progress.progress_percent,
        currentStep: progress.current_step,
        queuePosition: progress.queue_position,
        errorMessage: progress.error_message,
        isPaused: progress.is_paused,
      });
    }

    if (!["done", "failed", "cancelled", "deleted"].includes(progress.status)) {
      notifiedTerminalRef.current = false;
    }

    if (progress.status === "failed") {
      setLastError(progress.error_message || "Unknown error");
    } else if (!["cancelled", "deleted"].includes(progress.status)) {
      setLastError(null);
    }
  }, [progress, videoId, updateJob, handleCancelComplete, cancelCompleted]);

  // On mount, track existing active video (skip after user cancelled)
  useEffect(() => {
    if (
      cancelCompleted ||
      cancelCompleteRef.current ||
      !existingVideoIsActive ||
      !existingVideo?.id ||
      videoId
    ) {
      return;
    }
    setVideoId(existingVideo.id);
    registerJob(existingVideo.id, story.id, existingVideo.status);
  }, [
    existingVideo,
    existingVideoIsActive,
    videoId,
    story.id,
    registerJob,
    cancelCompleted,
  ]);

  // FIX 12b: Validate background when it changes
  useEffect(() => {
    const validateBg = async () => {
      if (!settings.background_source) {
        setBgValidation({ valid: null, error: null, checking: false });
        return;
      }
      setBgValidation((prev) => ({ ...prev, checking: true }));
      try {
        const { data } = await videoApi.validateBackground({
          background_source: settings.background_source,
        });
        setBgValidation({
          valid: data.valid,
          error: data.error || null,
          checking: false,
        });
      } catch (e: any) {
        setBgValidation({
          valid: false,
          error: "Validation request failed",
          checking: false,
        });
      }
    };
    const timer = setTimeout(validateBg, 500); // debounce
    return () => clearTimeout(timer);
  }, [settings.background_source]);

  //     ELECTRON: Native file system dialogs
  const handleSelectFolderElectron = async () => {
    if (!window.electronAPI) return;
    const path = await window.electronAPI.selectDirectory();
    if (path) setSettings((s) => ({ ...s, background_source: path }));
  };

  const handleSelectFileElectron = async () => {
    if (!window.electronAPI) return;
    const path = await window.electronAPI.selectFile([
      { name: "Videos", extensions: ["mp4", "mov", "avi", "mkv", "webm"] },
    ]);
    if (path) setSettings((s) => ({ ...s, background_source: path }));
  };

  //     BROWSER: File System Access API
  const uploadSingleFile = async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);

    toast.loading("Uploading video...", { id: "bg-upload" });
    try {
      const { data } = await videoApi.uploadBackground(formData);
      toast.dismiss("bg-upload");
      if (data.valid) {
        setSettings((s) => ({ ...s, background_source: data.path }));
        toast.success("Video uploaded");
      } else {
        toast.error(data.error || "Upload failed");
      }
    } catch (e: any) {
      toast.dismiss("bg-upload");
      toast.error(e.response?.data?.detail || "Upload failed");
    }
  };

  const uploadDirectoryFiles = async (files: File[]) => {
    const videoExts = [".mp4", ".mov", ".avi", ".mkv", ".webm"];
    const videoFiles = files.filter((f) =>
      videoExts.some((ext) => f.name.toLowerCase().endsWith(ext)),
    );

    if (videoFiles.length === 0) {
      toast.error("No video files found in selection");
      return;
    }

    const formData = new FormData();
    formData.append("is_directory", "true");
    videoFiles.forEach((f) => formData.append("directory_files", f));

    toast.loading(`Uploading ${videoFiles.length} video(s)...`, {
      id: "bg-upload",
    });
    try {
      const { data } = await videoApi.uploadBackground(formData);
      toast.dismiss("bg-upload");
      if (data.valid) {
        setSettings((s) => ({ ...s, background_source: data.path }));
        toast.success(`${data.file_count} video(s) uploaded`);
      } else {
        toast.error(data.error || "Upload failed");
      }
    } catch (e: any) {
      toast.dismiss("bg-upload");
      toast.error(e.response?.data?.detail || "Upload failed");
    }
  };

  const handleSelectFolderBrowser = async () => {
    // Try File System Access API first
    try {
      const dirHandle = await (window as any).showDirectoryPicker?.();
      if (!dirHandle) return;

      const files: File[] = [];
      for await (const entry of dirHandle.values()) {
        if (entry.kind === "file") {
          const file = await entry.getFile();
          files.push(file);
        }
      }
      await uploadDirectoryFiles(files);
    } catch (err: any) {
      if (err.name === "AbortError") return;
      // Fallback to legacy input
      fallbackDirectoryUpload();
    }
  };

  const handleSelectFileBrowser = async () => {
    // Try File System Access API first
    try {
      const fileHandle = await (window as any).showOpenFilePicker?.({
        types: [
          {
            description: "Videos",
            accept: {
              "video/*": [".mp4", ".mov", ".avi", ".mkv", ".webm"],
            },
          },
        ],
      });
      if (fileHandle && fileHandle[0]) {
        const file = await fileHandle[0].getFile();
        await uploadSingleFile(file);
      }
    } catch (err: any) {
      if (err.name === "AbortError") return;
      // Fallback to legacy input
      fallbackFileUpload();
    }
  };

  //     BROWSER FALLBACKS: Legacy <input>
  const fallbackDirectoryUpload = () => {
    const input = document.createElement("input");
    input.type = "file";
    (input as any).webkitdirectory = true;
    input.onchange = async (e: any) => {
      const files = Array.from(e.target.files as FileList);
      await uploadDirectoryFiles(files);
    };
    input.click();
  };

  const fallbackFileUpload = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "video/*";
    input.onchange = async (e: any) => {
      const file = e.target.files?.[0];
      if (file) await uploadSingleFile(file);
    };
    input.click();
  };

  //     Unified handlers
  const handleSelectFolder = async () => {
    if (window.electronAPI) {
      await handleSelectFolderElectron();
    } else {
      await handleSelectFolderBrowser();
    }
  };

  const handleSelectFile = async () => {
    if (window.electronAPI) {
      await handleSelectFileElectron();
    } else {
      await handleSelectFileBrowser();
    }
  };

  const handleGenerate = async () => {
    if (hasStartedGeneration && isGenerating) {
      toast("Generation already in progress");
      return;
    }

    if (!settings.background_source) {
      toast.error("Please select a background video or folder");
      return;
    }

    // FIX 12b: Block generation if background is invalid
    if (bgValidation.valid === false) {
      toast.error(bgValidation.error || "Invalid background video source");
      return;
    }

    // Clean up previous state
    if (videoId) {
      removeJob(videoId);
    }
    setLastError(null);
    setHasStartedGeneration(true);
    setCancelCompleted(false);
    notifiedTerminalRef.current = false;
    cancelCompleteRef.current = false;

    try {
      const subtitleStyle: SubtitleStyleType = {
        position: settings.subtitle_position,
        font_size: settings.subtitle_size,
        font_color: "#FFFFFF",
        outline_color: "#000000",
        outline_width: 2,
        max_width_percent: 90,
      };

      const { data } = await videoApi.generate({
        story_id: story.id,
        include_updates: settings.include_updates,
        voice_id: settings.voice_id,
        background_source: settings.background_source,
        video_format: settings.video_format,
        subtitle_style: subtitleStyle,
        generate_hashtags: settings.generate_hashtags,
      });

      if (data.video_id !== undefined) {
        setVideoId(data.video_id);
        registerJob(data.video_id, story.id, data.status || "queued");

        if (data.queue_position) {
          toast.success(
            `Generation queued at position #${data.queue_position}`,
          );
        } else if (data.message?.includes("already exists")) {
          // This is the "already exists" case - just show info toast, don't open progress
          toast(data.message);
          // Don't track this as an active generation
          setHasStartedGeneration(false);
          // But still set videoId so user can see progress if they want
          setVideoId(data.video_id);
        } else if (data.message?.includes("retry")) {
          toast.success(data.message);
        } else {
          toast.success(data.message || "Generation started!");
        }
      }
    } catch (e: any) {
      const backendDetail = e.response?.data?.detail;
      const msg = backendDetail || "Failed to start video generation";

      const displayError =
        backendDetail?.includes("not installed") ||
        backendDetail?.includes("TTS model")
          ? backendDetail
          : msg;

      toast.error(displayError);
      setLastError(displayError);
      setHasStartedGeneration(false);
    }
  };

  const handleRetry = async () => {
    if (!videoId) return;

    removeJob(videoId);
    setLastError(null);
    setHasStartedGeneration(true);
    setCancelCompleted(false);
    notifiedTerminalRef.current = false;
    cancelCompleteRef.current = false;

    try {
      const { data } = await videoApi.retry(videoId);
      if (data.video_id) {
        setVideoId(data.video_id);
        registerJob(data.video_id, story.id, "queued");
        toast.success(data.message || "Generation retry queued");
      }
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Retry failed");
      setHasStartedGeneration(false);
    }
  };

  const handlePause = async () => {
    if (!videoId) return;
    try {
      await videoApi.pause(videoId);
      toast.success("Generation paused");
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to pause");
    }
  };

  const handleResume = async () => {
    if (!videoId) return;
    try {
      await videoApi.resume(videoId);
      toast.success("Generation resuming...");
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to resume");
    }
  };

  const handleCancel = async () => {
    if (!videoId || isCancelling) return;
    setIsCancelling(true);
    const id = videoId;
    try {
      await videoApi.cancel(id);
      handleCancelComplete(id);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to cancel");
      setIsCancelling(false);
    }
  };

  // Animated ellipsis cycling through "." ".." "..."
  const [ellipsis, setEllipsis] = useState(".");
  const activeStep = progress?.current_step ?? (existingVideoIsActive ? existingVideo?.current_step : null);
  const isAnimating = activeStep ? ANIMATING_STATUSES.has(activeStep) : false;

  useEffect(() => {
    if (!isAnimating) return;
    const cycle = [".", "..", "..."];
    let idx = 0;
    const timer = setInterval(() => {
      idx = (idx + 1) % cycle.length;
      setEllipsis(cycle[idx]);
    }, 400);
    return () => clearInterval(timer);
  }, [isAnimating]);

  const rawStepLabel = progress
    ? (progress.status_message || STEP_LABELS[progress.current_step] || progress.current_step)
    : existingVideoIsActive
      ? STEP_LABELS[existingVideo!.current_step] || "Processing..."
      : "";

  const currentStepLabel = isAnimating
    ? rawStepLabel.replace(/\.{0,3}$/, "") + ellipsis
    : rawStepLabel;

  const currentProgress =
    progress?.progress_percent ??
    (existingVideoIsActive ? existingVideo!.progress_percent : 0);

  const queuePosition =
    progress?.queue_position ?? existingVideo?.queue_position;

  // Determine what view to show
  const showProgress =
    !cancelCompleted && ((isGenerating && !isDone) || isCancelling);
  const showDone = isDone && !isCancelling && !cancelCompleted;
  const showPicker = !showProgress && !showDone;

  const handleClose = useCallback(() => {
    videoProgressSSE.disconnect();
    setActiveModal(null, null);
    onClose();
  }, [onClose, setActiveModal]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-surface-light dark:bg-surface-dark rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-xl">
        <div className="flex items-center justify-between p-6 border-b border-border-light dark:border-border-dark">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
              <Film className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Generate Video</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 truncate max-w-md">
                {story.title}
              </p>
            </div>
          </div>
          <button
            onClick={handleClose}
            className="cursor-pointer p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-white/5"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {showProgress ? (
            <div className="space-y-4">
              <div className="text-center py-6">
                <div className="relative w-20 h-20 mx-auto mb-4">
                  <div className="absolute inset-0 rounded-full border-4 border-primary/20" />
                  {isCancelling ? (
                    <>
                      <div className="absolute inset-0 rounded-full border-4 border-red-500/20" />
                      <div className="absolute inset-0 rounded-full border-4 border-red-500 border-t-transparent animate-spin" />
                      <X className="absolute inset-0 m-auto w-8 h-8 text-red-500" />
                    </>
                  ) : (
                    <>
                      <div
                        className="absolute inset-0 rounded-full border-4 border-primary border-t-transparent animate-spin"
                        style={{
                          animationPlayState: isPaused ? "paused" : "running",
                        }}
                      />
                      <Film className="absolute inset-0 m-auto w-8 h-8 text-primary" />
                    </>
                  )}
                </div>
                <h3 className="text-lg font-semibold mb-1">
                  {isCancelling
                    ? "Cancelling..."
                    : isPaused
                      ? "Generation Paused"
                      : isFailed
                        ? "Generation Failed"
                        : queuePosition
                          ? `Queued #${queuePosition}`
                          : "Generating Video..."}
                </h3>
                <p className="text-sm text-gray-500 mb-4">{currentStepLabel}</p>

                <div className="w-full max-w-md mx-auto mb-4">
                  <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full transition-all duration-500"
                      style={{ width: `${currentProgress}%` }}
                    />
                  </div>
                  {queuePosition && queuePosition > 0 && (
                    <div className="flex justify-end mt-1">
                      <span className="text-xs text-yellow-600 flex items-center gap-1">
                        <ListOrdered className="w-3 h-3" />
                        Queue #{queuePosition}
                      </span>
                    </div>
                  )}
                </div>

                {/* Progress percentage displayed prominently */}
                {currentProgress > 0 && (
                  <div className="text-2xl font-bold text-primary mt-1">
                    {currentProgress}%
                  </div>
                )}

                {(progress?.error_message || existingVideo?.error_message) && (
                  <div className="mt-3 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg text-left max-w-md mx-auto">
                    <p className="text-sm text-red-600 dark:text-red-400 font-medium">
                      Error{" "}
                      {progress?.error_step || existingVideo?.error_step
                        ? `at ${progress?.error_step || existingVideo?.error_step}`
                        : ""}
                    </p>
                    <p className="text-xs text-red-500 mt-1">
                      {progress?.error_message || existingVideo?.error_message}
                    </p>
                  </div>
                )}

                <p className="text-xs text-gray-400 mt-3">
                  {isGenerating && !isDone
                    ? "Generation continues in background if you close this modal"
                    : ""}
                </p>
              </div>

              <div className="flex items-center justify-center gap-3">
                {isPaused ? (
                  <button
                    onClick={handleResume}
                    className="cursor-pointer btn-primary flex items-center gap-2"
                  >
                    <Play className="w-4 h-4" />
                    Resume
                  </button>
                ) : isFailed ? (
                  <button
                    onClick={handleRetry}
                    className="cursor-pointer btn-primary flex items-center gap-2"
                  >
                    <RotateCw className="w-4 h-4" />
                    Retry
                  </button>
                ) : (
                  <button
                    onClick={handlePause}
                    disabled={!isGenerating || isDone || isCancelling}
                    className="cursor-pointer btn-secondary flex items-center gap-2 disabled:opacity-50"
                  >
                    <Pause className="w-4 h-4" />
                    Pause
                  </button>
                )}
                <button
                  onClick={handleCancel}
                  disabled={isDone || isCancelled || isCancelling}
                  className="cursor-pointer px-4 py-2 bg-red-50 dark:bg-red-900/20 text-red-500 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 flex items-center gap-2 font-medium disabled:opacity-50"
                >
                  {isCancelling ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Cancelling...
                    </>
                  ) : (
                    <>
                      <X className="w-4 h-4" />
                      Cancel
                    </>
                  )}
                </button>
              </div>
            </div>
          ) : showDone ? (
            <div className="text-center py-8 space-y-4">
              <div className="w-16 h-16 mx-auto rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                <CheckCircle className="w-8 h-8 text-green-500" />
              </div>
              <div>
                <h3 className="text-lg font-semibold">Video Ready!</h3>
                <p className="text-sm text-gray-500">
                  Your video has been generated successfully.
                </p>
              </div>
              {hasExistingVideo && existingVideo?.video_path && (
                <div className="text-xs text-gray-400">
                  <code className="bg-gray-100 dark:bg-surface-dark px-2 py-1 rounded">
                    {existingVideo.video_path}
                  </code>
                </div>
              )}
              <button onClick={onClose} className="cursor-pointer btn-primary">
                Close
              </button>
            </div>
          ) : showPicker ? (
            <>
              {isUpdate && parentStory && (
                <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
                  <p className="text-sm text-blue-700 dark:text-blue-300">
                    This is an update to{" "}
                    <span className="font-medium">{parentStory.title}</span>.
                    {settings.include_updates
                      ? " It will be included in the parent video."
                      : " Generating separately from the parent story."}
                  </p>
                </div>
              )}

              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                  <Mic className="w-4 h-4" />
                  Voice
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">
                    Select Voice
                  </label>
                  <select
                    value={settings.voice_id}
                    onChange={(e) =>
                      setSettings((s) => ({ ...s, voice_id: e.target.value }))
                    }
                    className="input w-full"
                    disabled={!voices || voices.length === 0}
                  >
                    {voices && voices.length > 0 ? (
                      voices.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.name}
                        </option>
                      ))
                    ) : (
                      <option value="default">No voices available</option>
                    )}
                  </select>
                  {voices && voices.length > 0 && (
                    <p className="text-xs text-gray-400 mt-1">
                      First use downloads the voice model (~500MB).
                    </p>
                  )}
                  {(!voices || voices.length === 0) && (
                    <p className="text-xs text-yellow-600 mt-1">
                      Install a TTS model in Settings to enable voice selection.
                    </p>
                  )}
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                  <Image className="w-4 h-4" />
                  Background Video
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={handleSelectFolder}
                    className="cursor-pointer btn-secondary flex items-center gap-2"
                  >
                    <FolderOpen className="w-4 h-4" />
                    Select Folder
                  </button>
                  <button
                    onClick={handleSelectFile}
                    className="cursor-pointer btn-secondary flex items-center gap-2"
                  >
                    <FileVideo className="w-4 h-4" />
                    Select Video File
                  </button>
                </div>
                {settings.background_source && (
                  <span className="text-sm text-gray-600 dark:text-gray-400 truncate flex-1 block">
                    {settings.background_source}
                  </span>
                )}
                {/* FIX 12b: Show validation status */}
                {bgValidation.checking && (
                  <p className="text-xs text-blue-500 flex items-center gap-1">
                    <span className="inline-block w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                    Validating background...
                  </p>
                )}
                {bgValidation.valid === true && (
                  <p className="text-xs text-green-600 flex items-center gap-1">
                    <CheckCircle className="w-3 h-3" />
                    Background source is valid
                  </p>
                )}
                {bgValidation.valid === false && (
                  <p className="text-xs text-red-500 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" />
                    {bgValidation.error || "Invalid background source"}
                  </p>
                )}
                <p className="text-xs text-gray-500">
                  {window.electronAPI
                    ? "Select a folder with video files or a specific video file."
                    : "In browser mode, videos are uploaded to the server for processing."}
                </p>
              </div>

              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                  <Settings className="w-4 h-4" />
                  Video Format
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={() =>
                      setSettings((s) => ({ ...s, video_format: "shorts" }))
                    }
                    className={`cursor-pointer flex-1 p-3 rounded-lg border-2 ${
                      settings.video_format === "shorts"
                        ? "border-primary bg-primary/5"
                        : "border-border-light dark:border-border-dark hover:bg-gray-50 dark:hover:bg-white/5"
                    }`}
                  >
                    <div className="text-sm font-medium">Shorts</div>
                    <div className="text-xs text-gray-500">9:16 Vertical</div>
                  </button>
                  <button
                    onClick={() =>
                      setSettings((s) => ({ ...s, video_format: "normal" }))
                    }
                    className={`cursor-pointer flex-1 p-3 rounded-lg border-2 ${
                      settings.video_format === "normal"
                        ? "border-primary bg-primary/5"
                        : "border-border-light dark:border-border-dark hover:bg-gray-50 dark:hover:bg-white/5"
                    }`}
                  >
                    <div className="text-sm font-medium">Normal</div>
                    <div className="text-xs text-gray-500">16:9 Horizontal</div>
                  </button>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                  <Type className="w-4 h-4" />
                  Subtitle Style
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">
                      Position
                    </label>
                    <select
                      value={settings.subtitle_position}
                      onChange={(e) =>
                        setSettings((s) => ({
                          ...s,
                          subtitle_position: e.target.value as any,
                        }))
                      }
                      className="input"
                    >
                      <option value="center">Center</option>
                      <option value="bottom">Bottom</option>
                      <option value="top">Top</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">
                      Font Size
                    </label>
                    <input
                      type="number"
                      value={settings.subtitle_size}
                      onChange={(e) =>
                        setSettings((s) => ({
                          ...s,
                          subtitle_size: parseInt(e.target.value),
                        }))
                      }
                      className="input"
                      min={20}
                      max={80}
                    />
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.include_updates}
                    onChange={(e) =>
                      setSettings((s) => ({
                        ...s,
                        include_updates: e.target.checked,
                      }))
                    }
                    className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary"
                  />
                  <span className="text-sm">
                    Include linked updates in video
                  </span>
                </label>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.generate_hashtags}
                    onChange={(e) =>
                      setSettings((s) => ({
                        ...s,
                        generate_hashtags: e.target.checked,
                      }))
                    }
                    className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary"
                  />
                  <span className="text-sm">
                    Auto-generate YouTube hashtags
                  </span>
                </label>
              </div>

              {lastError && (
                <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-sm font-medium text-red-600 dark:text-red-400">
                        Generation failed
                      </p>
                      <p className="text-xs text-red-500 mt-1">{lastError}</p>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-8">
              <p className="text-gray-500">Setting up video generation...</p>
            </div>
          )}
        </div>

        {showPicker && (
          <div className="flex items-center justify-end gap-3 p-6 border-t border-border-light dark:border-border-dark">
            <button onClick={onClose} className="cursor-pointer btn-secondary">
              Cancel
            </button>
            <button
              onClick={handleGenerate}
              disabled={
                !settings.background_source ||
                hasStartedGeneration ||
                bgValidation.valid === false ||
                bgValidation.checking
              }
              className="cursor-pointer btn-primary flex items-center gap-2 disabled:opacity-50"
            >
              <Film className="w-4 h-4" />
              Generate Video
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
