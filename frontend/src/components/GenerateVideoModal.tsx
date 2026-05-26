import { useState, useEffect, useCallback, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  X,
  Film,
  Mic,
  Type,
  Image,
  Settings,
  Pause,
  Play,
  Square,
  FolderOpen,
  FileVideo,
  CheckCircle,
  AlertTriangle,
  RotateCw,
  ListOrdered,
} from "lucide-react";
import { videoApi, ttsLocalApi, settingsApi } from "@/services/api";
import type { Story, SubtitleStyle as SubtitleStyleType } from "@/types";
import { useVideoProgress } from "@/hooks/useVideoProgress";
import { useVideoJobsStore } from "@/store/videoJobs";
import { ACTIVE_GENERATION_STATUSES } from "@/config/videoStatus";
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

const STEP_ORDER: string[] = [
  "queued",
  "preparing",
  "tts",
  "tts_synthesizing",
  "tts_done",
  "transcribing",
  "transcribe_done",
  "generating_subtitles",
  "subtitles_done",
  "selecting_background",
  "compositing",
  "ffmpeg_processing",
  "compositing_done",
  "generating_thumbnail",
  "thumbnail",
  "done",
];

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
  const { setActiveModal, registerJob, updateJob, removeJob } =
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

  // CRITICAL FIX: Track if we already showed the cancel toast to prevent double-toast
  const cancelToastShownRef = useRef(false);
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

  // Load default voice
  useEffect(() => {
    const loadDefault = async () => {
      try {
        const { data } = await settingsApi.get("default_tts_voice");
        if (data?.value) {
          setSettings((s) => ({ ...s, voice_id: data.value }));
          return;
        }
      } catch (e: any) {
        if (e?.response?.status !== 404) {
          console.debug("Failed to load default voice:", e);
        }
      }
      if (voices && voices.length > 0) {
        setSettings((s) => ({ ...s, voice_id: voices[0].id }));
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

  const handleError = useCallback((data: any) => {
    if (!notifiedTerminalRef.current) {
      notifiedTerminalRef.current = true;
      if (data.status === "failed") {
        toast.error(data.error_message || "Video generation failed");
      } else if (data.status === "cancelled") {
        // CRITICAL FIX: Only show toast if we haven't already shown it from handleCancel
        if (!cancelToastShownRef.current) {
          toast("Generation cancelled", { icon: "⚠️" });
        }
      }
    }
  }, []);

  const { progress } = useVideoProgress({
    videoId,
    onComplete: handleComplete,
    onError: handleError,
  });

  // Derive UI state from progress
  const isGenerating = progress
    ? ACTIVE_GENERATION_STATUSES.includes(progress.status)
    : existingVideoIsActive;

  const isPaused = progress?.status === "paused";
  const isFailed = progress?.status === "failed" || lastError !== null;
  const isDone =
    progress?.status === "done" ||
    (hasExistingVideo && existingVideo?.status === "done");
  const isCancelled = progress?.status === "cancelled";

  // Sync progress state with store
  useEffect(() => {
    if (!progress) return;

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

    // Reset terminal notification when we see a non-terminal state
    if (!["done", "failed", "cancelled"].includes(progress.status)) {
      notifiedTerminalRef.current = false;
      cancelToastShownRef.current = false;
    }

    if (["done", "failed", "cancelled"].includes(progress.status)) {
      if (progress.status === "failed") {
        setLastError(progress.error_message || "Unknown error");
      }
    } else {
      setLastError(null);
    }
  }, [progress, videoId, updateJob]);

  // On mount, track existing active video
  useEffect(() => {
    if (existingVideoIsActive && existingVideo?.id && !videoId) {
      setVideoId(existingVideo.id);
      registerJob(existingVideo.id, story.id, existingVideo.status);
    }
  }, [existingVideo, existingVideoIsActive, videoId, story.id, registerJob]);

  const handleSelectFolder = async () => {
    if (window.electronAPI) {
      const path = await window.electronAPI.selectDirectory();
      if (path) setSettings((s) => ({ ...s, background_source: path }));
    } else {
      try {
        const dirHandle = await (window as any).showDirectoryPicker?.();
        if (dirHandle)
          setSettings((s) => ({ ...s, background_source: dirHandle.name }));
      } catch (err: any) {
        if (err.name === "AbortError") return;
        const input = document.createElement("input");
        input.type = "file";
        (input as any).webkitdirectory = true;
        input.onchange = (e: any) => {
          const files = e.target.files;
          if (files.length > 0) {
            const firstFile = files[0];
            const path = firstFile.webkitRelativePath
              ? firstFile.webkitRelativePath.split("/")[0]
              : firstFile.name;
            setSettings((s) => ({ ...s, background_source: path }));
          }
        };
        input.click();
      }
    }
  };

  const handleSelectFile = async () => {
    if (window.electronAPI) {
      const path = await window.electronAPI.selectFile([
        { name: "Videos", extensions: ["mp4", "mov", "avi", "mkv", "webm"] },
      ]);
      if (path) setSettings((s) => ({ ...s, background_source: path }));
    } else {
      try {
        const fileHandle = await (window as any).showOpenFilePicker?.({
          types: [
            {
              description: "Videos",
              accept: { "video/*": [".mp4", ".mov", ".avi", ".mkv", ".webm"] },
            },
          ],
        });
        if (fileHandle && fileHandle[0]) {
          const file = await fileHandle[0].getFile();
          setSettings((s) => ({ ...s, background_source: file.name }));
        }
      } catch (err: any) {
        if (err.name === "AbortError") return;
        const input = document.createElement("input");
        input.type = "file";
        input.accept = "video/*";
        input.onchange = (e: any) => {
          const file = e.target.files?.[0];
          if (file)
            setSettings((s) => ({ ...s, background_source: file.name }));
        };
        input.click();
      }
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

    // Clean up previous state
    if (videoId) {
      removeJob(videoId);
    }
    setLastError(null);
    setHasStartedGeneration(true);
    notifiedTerminalRef.current = false;
    cancelToastShownRef.current = false;

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
    notifiedTerminalRef.current = false;
    cancelToastShownRef.current = false;

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
    if (!videoId) return;
    try {
      await videoApi.cancel(videoId);
      // CRITICAL FIX: Mark that we showed the toast, so SSE handler won't double-toast
      cancelToastShownRef.current = true;
      toast.success("Generation cancelled");
      setHasStartedGeneration(false);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to cancel");
    }
  };

  const currentStepLabel = progress
    ? STEP_LABELS[progress.current_step] || progress.current_step
    : existingVideoIsActive
      ? STEP_LABELS[existingVideo.current_step] || "Processing..."
      : "";

  const currentProgress =
    progress?.progress_percent ??
    (existingVideoIsActive ? existingVideo!.progress_percent : 0);

  const queuePosition =
    progress?.queue_position ?? existingVideo?.queue_position;

  const currentStepIndex = progress
    ? STEP_ORDER.indexOf(progress.current_step)
    : -1;

  // Determine what view to show
  const showProgress = isGenerating && !isDone;
  const showDone = isDone;
  const showPicker = !showProgress && !showDone && !isCancelled;
  const showCancelled = isCancelled && !showPicker;

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
            onClick={onClose}
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
                  <div
                    className="absolute inset-0 rounded-full border-4 border-primary border-t-transparent animate-spin"
                    style={{
                      animationPlayState: isPaused ? "paused" : "running",
                    }}
                  />
                  <Film className="absolute inset-0 m-auto w-8 h-8 text-primary" />
                </div>
                <h3 className="text-lg font-semibold mb-1">
                  {isPaused
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
                  <div className="flex justify-between mt-1">
                    <span className="text-xs text-gray-400">
                      {currentProgress}%
                    </span>
                    {queuePosition && queuePosition > 0 && (
                      <span className="text-xs text-yellow-600 flex items-center gap-1">
                        <ListOrdered className="w-3 h-3" />
                        Queue #{queuePosition}
                      </span>
                    )}
                  </div>
                </div>

                {currentStepIndex >= 0 && (
                  <div className="w-full max-w-md mx-auto mt-4">
                    <div className="grid grid-cols-4 gap-1 text-xs">
                      {[
                        { key: "queued", label: "Queue" },
                        { key: "preparing", label: "Prepare" },
                        { key: "tts", label: "TTS" },
                        { key: "tts_done", label: "TTS Done" },
                        { key: "transcribe_done", label: "Transcribe" },
                        { key: "subtitles_done", label: "Subtitles" },
                        { key: "selecting_background", label: "BG" },
                        { key: "compositing", label: "Compose" },
                        { key: "compositing_done", label: "Finalize" },
                        { key: "generating_thumbnail", label: "Thumb" },
                        { key: "done", label: "Done" },
                      ].map((step) => {
                        const stepIdx = STEP_ORDER.indexOf(step.key);
                        const isActive = currentStepIndex === stepIdx;
                        const isDone = currentStepIndex > stepIdx;
                        return (
                          <div
                            key={step.key}
                            className={`px-1 py-1 rounded text-center transition-all ${
                              isActive
                                ? "bg-primary text-white font-medium"
                                : isDone
                                  ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400"
                                  : "bg-gray-100 dark:bg-gray-800 text-gray-400"
                            }`}
                          >
                            {step.label}
                          </div>
                        );
                      })}
                    </div>
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
                    disabled={!isGenerating || isDone}
                    className="cursor-pointer btn-secondary flex items-center gap-2 disabled:opacity-50"
                  >
                    <Pause className="w-4 h-4" />
                    Pause
                  </button>
                )}
                <button
                  onClick={handleCancel}
                  disabled={isDone || isCancelled}
                  className="cursor-pointer px-4 py-2 bg-red-50 dark:bg-red-900/20 text-red-500 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 flex items-center gap-2 font-medium disabled:opacity-50"
                >
                  <Square className="w-4 h-4" />
                  Cancel
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
          ) : showCancelled ? (
            <div className="text-center py-8 space-y-4">
              <div className="w-16 h-16 mx-auto rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
                <Square className="w-8 h-8 text-gray-500" />
              </div>
              <div>
                <h3 className="text-lg font-semibold">Generation Cancelled</h3>
                <p className="text-sm text-gray-500">
                  The video generation was cancelled.
                </p>
              </div>
              <div className="flex items-center justify-center gap-3">
                <button
                  onClick={() => {
                    setVideoId(null);
                    notifiedTerminalRef.current = false;
                    cancelToastShownRef.current = false;
                  }}
                  className="cursor-pointer btn-primary"
                >
                  Start New Generation
                </button>
                <button
                  onClick={onClose}
                  className="cursor-pointer btn-secondary"
                >
                  Close
                </button>
              </div>
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
                <p className="text-xs text-gray-500">
                  Select a folder with video files (one will be picked randomly)
                  or a specific video file.
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
              disabled={!settings.background_source || hasStartedGeneration}
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
