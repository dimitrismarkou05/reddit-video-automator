import { useState, useEffect } from "react";
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
} from "lucide-react";
import { videoApi, ttsLocalApi, settingsApi } from "@/services/api";
import type { Story, SubtitleStyle } from "@/types";
import { useVideoProgress } from "@/hooks/useVideoProgress";
import { ProgressBar } from "@/components/common/ProgressBar";
import { ACTIVE_GENERATION_STATUSES } from "@/config/videoStatus";
import toast from "react-hot-toast";

const STEP_LABELS: Record<string, string> = {
  queued: "Queued...",
  preparing: "Preparing narrative...",
  tts: "Generating speech...",
  tts_done: "TTS complete",
  transcribe_done: "Transcription complete",
  subtitles_done: "Subtitles generated",
  selecting_background: "Selecting background...",
  compositing: "Compositing video...",
  compositing_done: "Finalizing...",
  thumbnail: "Generating thumbnail...",
  done: "Complete!",
  failed: "Failed",
  cancelled: "Cancelled",
  paused: "Paused",
};

interface GenerateVideoModalProps {
  story: Story;
  onClose: () => void;
  existingVideoId?: number | null;
}

export function GenerateVideoModal({
  story,
  onClose,
  existingVideoId,
}: GenerateVideoModalProps) {
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
  const [isGenerating, setIsGenerating] = useState(existingVideoIsActive);
  const [showBackgroundPicker, setShowBackgroundPicker] = useState(
    !existingVideoIsActive &&
      !(hasExistingVideo && existingVideo?.status === "done"),
  );
  const [lastError, setLastError] = useState<string | null>(null);
  const [hasStartedGeneration, setHasStartedGeneration] = useState(false);

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
      // No saved default: auto-select first available voice
      if (voices && voices.length > 0) {
        setSettings((s) => ({ ...s, voice_id: voices[0].id }));
      }
    };
    loadDefault();
  }, [voices]);

  // Track video progress via SSE
  const { progress } = useVideoProgress({
    videoId,
    onComplete: (data) => {
      if (data.status === "done") {
        toast.success("Video generation complete!");
      } else if (data.status === "failed") {
        toast.error(data.error_message || "Video generation failed");
      }
    },
  });

  // Sync progress state with UI
  useEffect(() => {
    if (!progress) {
      // If no progress but we have an existing active video, still show generating
      if (existingVideoIsActive && videoId) {
        setIsGenerating(true);
        setShowBackgroundPicker(false);
      }
      return;
    }

    const terminal = ["done", "failed", "cancelled"];
    if (terminal.includes(progress.status)) {
      setIsGenerating(false);
      if (progress.status === "failed") {
        setLastError(progress.error_message || "Unknown error");
        setShowBackgroundPicker(true);
        setVideoId(null);
      } else if (progress.status === "cancelled") {
        setShowBackgroundPicker(true);
        setVideoId(null);
      } else if (progress.status === "done") {
        setShowBackgroundPicker(false);
      }
    } else {
      setIsGenerating(true);
      setShowBackgroundPicker(false);
      setLastError(null);
    }
  }, [progress, existingVideoIsActive, videoId]);

  // On mount, if there's an existing active video, ensure we're tracking it
  useEffect(() => {
    if (existingVideoIsActive && existingVideo?.id && !videoId) {
      setVideoId(existingVideo.id);
      setIsGenerating(true);
      setShowBackgroundPicker(false);
    }
  }, [existingVideo, existingVideoIsActive, videoId]);

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
    // Prevent double-submission
    if (hasStartedGeneration || isGenerating) {
      toast("Generation already in progress");
      return;
    }

    if (!settings.background_source) {
      toast.error("Please select a background video or folder");
      return;
    }

    setLastError(null);
    setIsGenerating(true);
    setShowBackgroundPicker(false);
    setHasStartedGeneration(true);

    try {
      const subtitleStyle: SubtitleStyle = {
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

      setVideoId(data.video_id);
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
      setIsGenerating(false);
      setShowBackgroundPicker(true);
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
      toast.success("Generation cancelled");
      setIsGenerating(false);
      setShowBackgroundPicker(true);
      setVideoId(null);
      setHasStartedGeneration(false);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to cancel");
    }
  };

  const isActive =
    progress && ACTIVE_GENERATION_STATUSES.includes(progress.status);
  const isPaused = progress?.status === "paused";
  const currentStepLabel = progress
    ? STEP_LABELS[progress.current_step] || progress.current_step
    : existingVideoIsActive
      ? STEP_LABELS[existingVideo.current_step] || "Processing..."
      : "";
  const currentProgress =
    progress?.progress_percent ??
    (existingVideoIsActive ? existingVideo!.progress_percent : 0);

  // Determine what view to show
  const showProgress =
    isGenerating ||
    (progress && !["done", "failed", "cancelled"].includes(progress.status));
  const showDone =
    progress?.status === "done" ||
    (hasExistingVideo && existingVideo?.status === "done");
  const showPicker = showBackgroundPicker && !showProgress && !showDone;

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
                  {isPaused ? "Generation Paused" : "Generating Video..."}
                </h3>
                <p className="text-sm text-gray-500 mb-4">{currentStepLabel}</p>

                <ProgressBar
                  progress={currentProgress}
                  size="lg"
                  showPercentage
                />

                {(progress?.queue_position || existingVideo?.queue_position) &&
                  ((progress?.queue_position ?? 0) > 0 ||
                    (existingVideo?.queue_position ?? 0) > 0) && (
                    <p className="text-sm text-yellow-600 mt-2">
                      Queued at position{" "}
                      {progress?.queue_position ||
                        existingVideo?.queue_position}
                    </p>
                  )}

                {(progress?.error_message || existingVideo?.error_message) && (
                  <div className="mt-3 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg text-left">
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
                  {isActive
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
                ) : (
                  <button
                    onClick={handlePause}
                    disabled={!isActive}
                    className="cursor-pointer btn-secondary flex items-center gap-2 disabled:opacity-50"
                  >
                    <Pause className="w-4 h-4" />
                    Pause
                  </button>
                )}
                <button
                  onClick={handleCancel}
                  className="cursor-pointer px-4 py-2 bg-red-50 dark:bg-red-900/20 text-red-500 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 flex items-center gap-2 font-medium"
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
          ) : showPicker ? (
            <>
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
