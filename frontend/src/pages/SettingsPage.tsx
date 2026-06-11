import { useState, useEffect, useCallback, useRef } from "react";
import {
  Key,
  Film,
  Palette,
  FolderOpen,
  Check,
  AlertCircle,
  Sun,
  Moon,
  Monitor,
  RotateCcw,
  Download,
  FolderInput,
  TestTube,
  Loader2,
  ChevronDown,
  ChevronUp,
  Clock,
  Zap,
  SlidersHorizontal,
  Gauge,
  Info,
} from "lucide-react";
import { useThemeStore, useAuthStore } from "@/store";
import { SettingsSection } from "@/components/settings/SettingsSection";
import { FfmpegStatus } from "@/components/ffmpeg/FfmpegStatus";
import { FfmpegInstallModal } from "@/components/ffmpeg/FfmpegInstallModal";
import { ffmpegApi, settingsApi, ffmpegSettingsApi } from "@/services/api";
import { useFfmpegStatus } from "@/hooks/useFfmpegStatus";
import { useTtsLocalStatus } from "@/hooks/useTtsLocalStatus";
import toast from "react-hot-toast";

interface CustomDropdownOption {
  value: string;
  label: string;
}

interface CustomDropdownProps {
  label: string;
  value: string;
  options: CustomDropdownOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  helpText?: string;
  icon?: React.ReactNode;
}

function CustomDropdown({
  label,
  value,
  options,
  onChange,
  disabled = false,
  helpText,
  icon,
}: CustomDropdownProps) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1.5 flex items-center gap-1.5">
        {icon && <span className="text-gray-400">{icon}</span>}
        {label}
      </label>
      <div className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className="input w-full appearance-none pr-10 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
      </div>
      {helpText && (
        <p className="text-xs text-gray-500 mt-1 flex items-center gap-1">
          <Info className="w-3 h-3" />
          {helpText}
        </p>
      )}
    </div>
  );
}

const QUALITY_OPTIONS: CustomDropdownOption[] = [
  { value: "draft", label: "Draft — fastest, lowest quality" },
  { value: "fast", label: "Fast — good for quick previews" },
  { value: "balanced", label: "Balanced — recommended" },
  { value: "quality", label: "High Quality — slower, better output" },
  { value: "archival", label: "Archival — slowest, best quality" },
];

const QUALITY_SPEED_HINTS: Record<string, string> = {
  draft: "~2-3x faster than balanced. Best for testing.",
  fast: "~1.5x faster than balanced. Good for drafts.",
  balanced: "Best balance of speed and quality.",
  quality: "~2-3x slower than balanced. Noticeably better compression.",
  archival:
    "~5-10x slower than balanced. Compositing may take many minutes — use for final exports only.",
};

const PRESET_SPEED_HINTS: Record<string, string> = {
  ultrafast: "~0.5x balanced compositing time. Largest output files.",
  superfast: "~0.7x balanced compositing time.",
  veryfast: "Baseline compositing speed (balanced default).",
  faster: "~1.2x balanced compositing time.",
  fast: "~1.5x balanced compositing time.",
  medium: "~2.5x balanced compositing time.",
  slow: "~5x balanced compositing time. Expect long renders.",
  slower: "~7x balanced compositing time. Not recommended for routine use.",
  veryslow:
    "~10x balanced compositing time. A 3-minute video may take 30+ minutes to compose.",
};

const SLOW_PRESETS = new Set(["slow", "slower", "veryslow"]);

/*                                                                  
   Advanced option configs
*/
const VIDEO_CODEC_OPTIONS: CustomDropdownOption[] = [
  { value: "libx264", label: "H.264 (libx264) — Best compatibility" },
  { value: "libx265", label: "H.265 / HEVC (libx265) — Better compression" },
  { value: "libvpx-vp9", label: "VP9 (libvpx-vp9) — Web optimized" },
];

const PRESET_OPTIONS: CustomDropdownOption[] = [
  { value: "ultrafast", label: "ultrafast — fastest encoding, largest file" },
  { value: "superfast", label: "superfast" },
  { value: "veryfast", label: "veryfast" },
  { value: "faster", label: "faster" },
  { value: "fast", label: "fast" },
  { value: "medium", label: "medium — default" },
  { value: "slow", label: "slow — better compression" },
  { value: "slower", label: "slower" },
  { value: "veryslow", label: "veryslow — best compression, slowest" },
];

const PIXEL_FORMAT_OPTIONS: CustomDropdownOption[] = [
  { value: "yuv420p", label: "yuv420p — Best compatibility" },
  { value: "yuv444p", label: "yuv444p — Full chroma (larger files)" },
  { value: "yuv422p", label: "yuv422p — Balanced chroma" },
  { value: "p010le", label: "p010le — 10-bit (HDR support)" },
];

const AUDIO_CODEC_OPTIONS: CustomDropdownOption[] = [
  { value: "aac", label: "AAC — Best compatibility" },
  { value: "libmp3lame", label: "MP3 — Wide support" },
  { value: "libopus", label: "Opus — Best quality at low bitrates" },
  { value: "flac", label: "FLAC — Lossless (large files)" },
];

const AUDIO_BITRATE_OPTIONS: CustomDropdownOption[] = [
  { value: "96k", label: "96 kbps — Low (voice only)" },
  { value: "128k", label: "128 kbps — Standard" },
  { value: "192k", label: "192 kbps — Good quality" },
  { value: "256k", label: "256 kbps — High quality" },
  { value: "320k", label: "320 kbps — Maximum" },
];

const AUDIO_SAMPLE_RATE_OPTIONS: CustomDropdownOption[] = [
  { value: "22050", label: "22050 Hz — Low" },
  { value: "44100", label: "44100 Hz — CD quality" },
  { value: "48000", label: "48000 Hz — Standard video" },
  { value: "96000", label: "96000 Hz — High-res audio" },
];

const CRF_OPTIONS: CustomDropdownOption[] = Array.from(
  { length: 18 },
  (_, i) => {
    const crf = i + 17; // 17 to 34
    const labels: Record<number, string> = {
      17: "17 — Visually lossless",
      18: "18 — Nearly lossless",
      20: "20 — High quality",
      23: "23 — Default (balanced)",
      26: "26 — Good compression",
      28: "28 — Aggressive compression",
      30: "30 — Smaller files",
    };
    return {
      value: String(crf),
      label: labels[crf] || `CRF ${crf}`,
    };
  },
);

const VIDEO_BITRATE_OPTIONS: CustomDropdownOption[] = [
  { value: "", label: "Auto (use CRF — recommended)" },
  { value: "1M", label: "1 Mbps — Low" },
  { value: "2M", label: "2 Mbps" },
  { value: "4M", label: "4 Mbps — Standard" },
  { value: "8M", label: "8 Mbps — High" },
  { value: "12M", label: "12 Mbps — Very high" },
  { value: "20M", label: "20 Mbps — Near lossless" },
];

export function SettingsPage() {
  const { isDark, toggle } = useThemeStore();
  const { authStatus } = useAuthStore();
  const [showInstallModal, setShowInstallModal] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isSavingPath, setIsSavingPath] = useState(false);
  const [ffmpegPath, setFfmpegPath] = useState("");
  const [ffprobePath, setFfprobePath] = useState("");

  const [defaultVoice, setDefaultVoice] = useState("");
  const [voices, setVoices] = useState<{ id: string; name: string }[]>([]);

  //    FFmpeg video settings
  const [videoSettings, setVideoSettings] = useState({
    quality: "balanced",
    video_codec: "libx264",
    video_preset: "veryfast",
    video_crf: "23",
    video_bitrate: "",
    pixel_format: "yuv420p",
    audio_codec: "aac",
    audio_bitrate: "192k",
    audio_sample_rate: "44100",
    ffmpeg_threads: "0",
    use_hardware_encoder: false,
  });
  const [isLoadingVideoSettings, setIsLoadingVideoSettings] = useState(true);
  const [showAdvancedVideo, setShowAdvancedVideo] = useState(false);
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { status: ffmpegStatus, refetch: refetchFfmpeg } = useFfmpegStatus();
  const { data: ttsStatus } = useTtsLocalStatus();

  // Load video generation settings on mount
  useEffect(() => {
    const loadVideoSettings = async () => {
      try {
        const { data } = await ffmpegSettingsApi.getAll();
        if (data) {
          setVideoSettings({
            quality: data.quality ?? "balanced",
            video_codec: data.video_codec ?? "libx264",
            video_preset: data.video_preset ?? "veryfast",
            video_crf: data.video_crf ?? "23",
            video_bitrate: data.video_bitrate ?? "",
            pixel_format: data.pixel_format ?? "yuv420p",
            audio_codec: data.audio_codec ?? "aac",
            audio_bitrate: data.audio_bitrate ?? "192k",
            audio_sample_rate: data.audio_sample_rate ?? "44100",
            ffmpeg_threads: data.ffmpeg_threads ?? "0",
            use_hardware_encoder: Boolean(data.use_hardware_encoder),
          });
        }
      } catch (e: any) {
        console.debug("Failed to load video settings:", e);
      } finally {
        setIsLoadingVideoSettings(false);
      }
    };
    loadVideoSettings();
  }, []);

  // Auto-save a video setting (debounced)
  const saveVideoSetting = useCallback(async (key: string, value: string) => {
    try {
      await ffmpegSettingsApi.set(key, value);
      console.debug(`[Settings] Saved ${key} = ${value}`);
    } catch (e: any) {
      toast.error(`Failed to save ${key}`);
      console.error(`[Settings] Failed to save ${key}:`, e);
    }
  }, []);

  // Debounced save for settings that change rapidly
  const queueSave = useCallback(
    (key: string, value: string) => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      saveTimeoutRef.current = setTimeout(() => {
        saveVideoSetting(key, value);
      }, 400);
    },
    [saveVideoSetting],
  );

  // Update a video setting: update local state immediately, save to backend
  const updateVideoSetting = useCallback(
    (key: string, value: string | boolean) => {
      setVideoSettings((prev) => ({ ...prev, [key]: value }));
      const apiKey = key === "quality" ? "video_quality" : key;
      const saveValue =
        typeof value === "boolean" ? (value ? "true" : "false") : value;
      queueSave(apiKey, saveValue);
    },
    [queueSave],
  );

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, []);

  //    Voice settings
  useEffect(() => {
    if (ttsStatus?.voices) {
      setVoices(ttsStatus.voices);
    }
  }, [ttsStatus]);

  useEffect(() => {
    const loadDefaultVoice = async () => {
      try {
        const { data } = await settingsApi.batchGet(["default_tts_voice"]);
        const saved = data?.default_tts_voice;
        if (saved && saved !== "default") {
          setDefaultVoice(saved);
          return;
        }
      } catch (e) {
        console.debug("Failed to load default voice:", e);
      }
      // No persisted default: auto-select and persist first available voice.
      if (voices.length > 0) {
        const fallbackId = voices[0].id;
        setDefaultVoice(fallbackId);
        try {
          await settingsApi.set("default_tts_voice", fallbackId);
        } catch {
          // non-critical
        }
      }
    };
    loadDefaultVoice();
  }, [voices]);

  const handleSelectOutputDir = async () => {
    if (window.electronAPI) {
      const path = await window.electronAPI.selectDirectory();
      if (path) {
        try {
          await settingsApi.set("output_directory", path);
          toast.success("Output directory saved");
        } catch (e) {
          toast.error("Failed to save output directory");
        }
      }
    }
  };

  const handleTestPath = async () => {
    if (!ffmpegPath.trim()) {
      toast.error("Please enter an FFmpeg path");
      return;
    }
    setIsTesting(true);
    try {
      const { data } = await ffmpegApi.checkPath(ffmpegPath.trim());
      if (data.valid) {
        toast.success(
          `Valid! Version: ${data.ffmpeg_version || data.ffprobe_version || "unknown"}`,
        );
      } else {
        toast.error(data.error || "Invalid path");
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to validate path");
    } finally {
      setIsTesting(false);
    }
  };

  const handleSetPath = async () => {
    if (!ffmpegPath.trim()) {
      toast.error("Please enter an FFmpeg path");
      return;
    }
    setIsSavingPath(true);
    try {
      const { data } = await ffmpegApi.setPath(
        ffmpegPath.trim(),
        ffprobePath.trim() || undefined,
      );
      if (data.valid) {
        toast.success("FFmpeg path saved successfully");
        refetchFfmpeg();
        setFfmpegPath("");
        setFfprobePath("");
      } else {
        toast.error(data.error || "Invalid path");
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save path");
    } finally {
      setIsSavingPath(false);
    }
  };

  const handleResetPaths = async () => {
    setIsResetting(true);
    try {
      await ffmpegApi.reset();
      toast.success("FFmpeg paths reset to defaults");
      refetchFfmpeg();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to reset paths");
    } finally {
      setIsResetting(false);
    }
  };

  const handleRetryDetection = async () => {
    setIsRetrying(true);
    try {
      const { data } = await ffmpegApi.getStatus();
      if (data.can_generate_videos) {
        toast.success("FFmpeg detected successfully");
      } else {
        toast.error(
          "FFmpeg not found. Try installing or setting a custom path.",
        );
      }
      refetchFfmpeg();
    } catch (e: any) {
      toast.error("Failed to detect FFmpeg");
    } finally {
      setIsRetrying(false);
    }
  };

  const handleSaveDefaultVoice = async () => {
    try {
      await settingsApi.set("default_tts_voice", defaultVoice);
      toast.success("Default voice saved");
    } catch (e) {
      toast.error("Failed to save default voice");
    }
  };

  const qualityBadgeColor = (() => {
    switch (videoSettings.quality) {
      case "draft":
        return "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400";
      case "fast":
        return "bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400";
      case "balanced":
        return "bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400";
      case "quality":
        return "bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400";
      case "archival":
        return "bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400";
      default:
        return "bg-gray-100 dark:bg-gray-800 text-gray-600";
    }
  })();

  const showSlowEncodingWarning =
    videoSettings.quality === "archival" ||
    SLOW_PRESETS.has(videoSettings.video_preset);

  const slowEncodingWarningMessage =
    videoSettings.quality === "archival"
      ? "Archival quality uses a slow encoding preset. Compositing can take 5-10x longer than balanced — reserve this for final exports."
      : `The "${videoSettings.video_preset}" preset is much slower than balanced. Compositing may take several minutes even for short videos.`;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold mb-6">Settings</h2>

      {/*     Video Generation Settings     */}
      <SettingsSection title="Video Generation" icon={Film}>
        <div className="space-y-5">
          {/* Quality — always visible */}
          <div className="p-4 bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark">
            <div className="flex items-center gap-2 mb-3">
              <Gauge className="w-4 h-4 text-primary" />
              <h4 className="text-sm font-semibold">Output Quality</h4>
              <span
                className={`ml-2 px-2 py-0.5 rounded-full text-xs font-medium ${qualityBadgeColor}`}
              >
                {QUALITY_OPTIONS.find(
                  (o) => o.value === videoSettings.quality,
                )?.label.split(" — ")[0] || videoSettings.quality}
              </span>
            </div>

            {isLoadingVideoSettings ? (
              <div className="flex items-center gap-2 text-sm text-gray-400 py-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                Loading settings...
              </div>
            ) : (
              <>
                <CustomDropdown
                  label="Quality Preset"
                  value={videoSettings.quality}
                  options={QUALITY_OPTIONS}
                  onChange={(val) => updateVideoSetting("quality", val)}
                  icon={<Film className="w-3.5 h-3.5" />}
                />

                {/* Speed hint */}
                <div className="mt-3 flex items-start gap-2 p-2.5 rounded-lg bg-primary/5 dark:bg-primary/10 border border-primary/10">
                  <Clock className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                  <p className="text-xs text-gray-600 dark:text-gray-300">
                    {QUALITY_SPEED_HINTS[videoSettings.quality]}
                  </p>
                </div>

                <div className="mt-3 flex items-start gap-2 p-2.5 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
                  <Info className="w-4 h-4 text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
                  <p className="text-xs text-blue-800 dark:text-blue-200">
                    Long videos on PCs with limited RAM are rendered in segments
                    automatically. Quality stays the same — rendering may take
                    longer instead of freezing your system.
                  </p>
                </div>

                {videoSettings.quality === "archival" && (
                  <div className="mt-3 flex items-start gap-2 p-2.5 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
                    <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                    <p className="text-xs text-amber-800 dark:text-amber-200">
                      Archival quality significantly increases compositing time.
                      Use balanced or fast for everyday videos.
                    </p>
                  </div>
                )}

                {/* Quality scale visual */}
                <div className="mt-3">
                  <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
                    <span className="flex items-center gap-1">
                      <Zap className="w-3 h-3" />
                      Faster
                    </span>
                    <span className="flex items-center gap-1">
                      Higher Quality
                      <Gauge className="w-3 h-3" />
                    </span>
                  </div>
                  <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-linear-to-r from-primary/30 via-primary to-primary/80 rounded-full transition-all duration-500"
                      style={{
                        width: `${((QUALITY_OPTIONS.findIndex((o) => o.value === videoSettings.quality) + 1) / QUALITY_OPTIONS.length) * 100}%`,
                      }}
                    />
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Advanced Video Settings — collapsible */}
          <div className="border border-border-light dark:border-border-dark rounded-xl overflow-hidden">
            <button
              onClick={() => setShowAdvancedVideo((v) => !v)}
              className="cursor-pointer w-full flex items-center justify-between p-4 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
            >
              <div className="flex items-center gap-2">
                <SlidersHorizontal className="w-4 h-4 text-gray-500" />
                <span className="text-sm font-medium">
                  Advanced Video Settings
                </span>
              </div>
              {showAdvancedVideo ? (
                <ChevronUp className="w-4 h-4 text-gray-400" />
              ) : (
                <ChevronDown className="w-4 h-4 text-gray-400" />
              )}
            </button>

            {showAdvancedVideo && (
              <div className="p-4 pt-4 space-y-4 border-t border-border-light dark:border-border-dark">
                <p className="text-xs text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/20 p-2.5 rounded-lg flex items-start gap-1.5">
                  <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  Changes apply to the next video you generate. These settings
                  override the quality preset.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <CustomDropdown
                    label="Video Codec"
                    value={videoSettings.video_codec}
                    options={VIDEO_CODEC_OPTIONS}
                    onChange={(val) => updateVideoSetting("video_codec", val)}
                    helpText="H.264 works everywhere. H.265 is smaller but slower."
                  />

                  <CustomDropdown
                    label="Encoding Preset"
                    value={videoSettings.video_preset}
                    options={PRESET_OPTIONS}
                    onChange={(val) => updateVideoSetting("video_preset", val)}
                    helpText="Slower presets = smaller files, longer compositing."
                  />

                  <div className="sm:col-span-2 flex items-start gap-2 p-2.5 rounded-lg bg-primary/5 dark:bg-primary/10 border border-primary/10">
                    <Clock className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                    <p className="text-xs text-gray-600 dark:text-gray-300">
                      {PRESET_SPEED_HINTS[videoSettings.video_preset] ||
                        "Relative compositing time vs balanced (veryfast)."}
                    </p>
                  </div>

                  {showSlowEncodingWarning && (
                    <div className="sm:col-span-2 flex items-start gap-2 p-2.5 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
                      <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                      <p className="text-xs text-amber-800 dark:text-amber-200">
                        {slowEncodingWarningMessage}
                      </p>
                    </div>
                  )}

                  <CustomDropdown
                    label="CRF (Quality)"
                    value={videoSettings.video_crf}
                    options={CRF_OPTIONS}
                    onChange={(val) => updateVideoSetting("video_crf", val)}
                    helpText="Lower = better quality, larger file. 23 is default."
                  />

                  <CustomDropdown
                    label="Video Bitrate"
                    value={videoSettings.video_bitrate}
                    options={VIDEO_BITRATE_OPTIONS}
                    onChange={(val) => updateVideoSetting("video_bitrate", val)}
                    helpText="Overrides CRF when set. Leave auto for best results."
                  />

                  <CustomDropdown
                    label="Pixel Format"
                    value={videoSettings.pixel_format}
                    options={PIXEL_FORMAT_OPTIONS}
                    onChange={(val) => updateVideoSetting("pixel_format", val)}
                    helpText="yuv420p is safest for compatibility."
                  />

                  <CustomDropdown
                    label="FFmpeg CPU Threads"
                    value={videoSettings.ffmpeg_threads}
                    options={[
                      { value: "0", label: "Auto (recommended)" },
                      { value: "1", label: "1 thread — slowest, lowest CPU" },
                      { value: "2", label: "2 threads" },
                      { value: "4", label: "4 threads" },
                      { value: "8", label: "8 threads — fastest on powerful PCs" },
                    ]}
                    onChange={(val) => updateVideoSetting("ffmpeg_threads", val)}
                    helpText="Auto adapts to your RAM. Lower threads keep the PC responsive."
                  />

                  <div className="sm:col-span-2 flex items-center gap-3 p-3 rounded-lg border border-border-light dark:border-border-dark">
                    <input
                      id="use-hw-encoder"
                      type="checkbox"
                      checked={videoSettings.use_hardware_encoder}
                      onChange={(e) =>
                        updateVideoSetting(
                          "use_hardware_encoder",
                          e.target.checked,
                        )
                      }
                      className="rounded border-gray-300"
                    />
                    <label htmlFor="use-hw-encoder" className="text-sm">
                      <span className="font-medium">Hardware video encoder</span>
                      <span className="block text-xs text-gray-500 mt-0.5">
                        Use GPU encoding (NVENC/AMF/QSV) when available. Same
                        quality settings; reduces CPU load.
                      </span>
                    </label>
                  </div>

                  <CustomDropdown
                    label="Audio Codec"
                    value={videoSettings.audio_codec}
                    options={AUDIO_CODEC_OPTIONS}
                    onChange={(val) => updateVideoSetting("audio_codec", val)}
                    helpText="AAC is the universal standard."
                  />

                  <CustomDropdown
                    label="Audio Bitrate"
                    value={videoSettings.audio_bitrate}
                    options={AUDIO_BITRATE_OPTIONS}
                    onChange={(val) => updateVideoSetting("audio_bitrate", val)}
                    helpText="192k is good quality for voice."
                  />

                  <CustomDropdown
                    label="Audio Sample Rate"
                    value={videoSettings.audio_sample_rate}
                    options={AUDIO_SAMPLE_RATE_OPTIONS}
                    onChange={(val) =>
                      updateVideoSetting("audio_sample_rate", val)
                    }
                    helpText="44100 Hz matches CD audio."
                  />
                </div>
              </div>
            )}
          </div>

          {/* Default Voice */}
          <div>
            <label className="block text-sm font-medium mb-1">
              Default Voice
            </label>
            <div className="flex gap-3">
              <div className="relative flex-1">
                <select
                  value={defaultVoice}
                  onChange={(e) => setDefaultVoice(e.target.value)}
                  className="input w-full appearance-none pr-10"
                  disabled={!ttsStatus?.installed}
                >
                  {voices.length === 0 && (
                    <option value="">No voices available</option>
                  )}
                  {voices.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>
              <button
                onClick={handleSaveDefaultVoice}
                disabled={!ttsStatus?.installed}
                className="cursor-pointer btn-primary flex items-center gap-2 disabled:opacity-50"
              >
                <Check className="w-4 h-4" />
                Save
              </button>
            </div>
            {!ttsStatus?.installed && (
              <p className="text-xs text-yellow-600 mt-1">
                TTS package not found. Reinstall the application.
              </p>
            )}
          </div>

          {/* Whisper Model Size */}
          <WhisperModelSizeSetting />

          {/* Output Directory */}
          <div>
            <label className="block text-sm font-medium mb-1">
              Output Directory
            </label>
            <div className="flex gap-3">
              <input
                type="text"
                readOnly
                placeholder="Select output folder..."
                className="input flex-1"
              />
              <button
                onClick={handleSelectOutputDir}
                className="cursor-pointer btn-secondary flex items-center gap-2"
              >
                <FolderOpen className="w-4 h-4" />
                Browse
              </button>
            </div>
          </div>

          {/* Default Video Format */}
          <div>
            <label className="block text-sm font-medium mb-1">
              Default Video Format
            </label>
            <div className="flex gap-3">
              <button className="cursor-pointer flex-1 p-3 rounded-lg border-2 border-primary bg-primary/5 text-center">
                <div className="text-sm font-medium">Shorts (9:16)</div>
                <div className="text-xs text-gray-500">
                  Vertical mobile format
                </div>
              </button>
              <button className="cursor-pointer flex-1 p-3 rounded-lg border-2 border-border-light dark:border-border-dark text-center hover:bg-gray-50 dark:hover:bg-white/5 ">
                <div className="text-sm font-medium">Normal (16:9)</div>
                <div className="text-xs text-gray-500">Standard horizontal</div>
              </button>
            </div>
          </div>

          {/* TTS Status */}
          <div className="border-t border-border-light dark:border-border-dark pt-4">
            <h4 className="text-sm font-medium mb-2">Text-to-Speech</h4>
            {ttsStatus?.installed ? (
              <div className="flex items-center gap-2 text-sm text-green-600 bg-green-50 dark:bg-green-900/20 p-3 rounded-lg">
                <Check className="w-4 h-4" />
                <span>
                  TTS ready. Voice model downloads on first use (~500MB).
                </span>
              </div>
            ) : (
              <div className="text-sm text-yellow-700 bg-yellow-50 dark:bg-yellow-900/20 p-3 rounded-lg">
                TTS package not found. Reinstall the application.
              </div>
            )}
          </div>
        </div>
      </SettingsSection>

      <SettingsSection title="YouTube Account" icon={Key}>
        {authStatus?.is_authenticated && authStatus.user_info ? (
          <div className="flex items-center gap-3 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
            {authStatus.user_info.picture ? (
              <img
                src={authStatus.user_info.picture}
                alt=""
                className="w-10 h-10 rounded-full"
              />
            ) : (
              <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center">
                <Monitor className="w-5 h-5 text-primary" />
              </div>
            )}
            <div>
              <p className="font-medium">{authStatus.user_info.name}</p>
              <p className="text-sm text-gray-500">
                {authStatus.user_info.email}
              </p>
            </div>
            <Check className="w-5 h-5 text-green-500 ml-auto" />
          </div>
        ) : (
          <div className="flex items-center gap-3 p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg">
            <AlertCircle className="w-5 h-5 text-yellow-500" />
            <p className="text-sm">
              Not connected. Go to Login to connect your Google account.
            </p>
          </div>
        )}
      </SettingsSection>

      <SettingsSection title="FFmpeg Configuration" icon={Film}>
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <FfmpegStatus />
          </div>

          {ffmpegStatus?.ffmpeg_path && (
            <div className="space-y-1 text-sm">
              <div className="flex items-center gap-2">
                <Check className="w-3.5 h-3.5 text-green-500" />
                <span className="text-gray-500">FFmpeg:</span>
                <code className="text-xs bg-gray-100 dark:bg-surface-dark dark:border dark:border-border-dark px-1.5 py-0.5 rounded truncate">
                  {ffmpegStatus.ffmpeg_path}
                </code>
              </div>
              {ffmpegStatus.ffmpeg_version && (
                <p className="text-xs text-gray-400 ml-5.5">
                  Version {ffmpegStatus.ffmpeg_version}
                </p>
              )}
            </div>
          )}

          {ffmpegStatus?.ffprobe_path && (
            <div className="space-y-1 text-sm">
              <div className="flex items-center gap-2">
                <Check className="w-3.5 h-3.5 text-green-500" />
                <span className="text-gray-500">FFprobe:</span>
                <code className="text-xs bg-gray-100 dark:bg-surface-dark dark:border dark:border-border-dark px-1.5 py-0.5 rounded truncate">
                  {ffmpegStatus.ffprobe_path}
                </code>
              </div>
              {ffmpegStatus.ffprobe_version && (
                <p className="text-xs text-gray-400 ml-5.5">
                  Version {ffmpegStatus.ffprobe_version}
                </p>
              )}
            </div>
          )}

          {!ffmpegStatus?.can_generate_videos && (
            <div className="p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
              <div className="flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-yellow-500 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-yellow-700 dark:text-yellow-400">
                    FFmpeg not detected
                  </p>
                  <p className="text-xs text-yellow-600 dark:text-yellow-300 mt-0.5">
                    Video generation is disabled. Install FFmpeg or set a custom
                    path.
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {!ffmpegStatus?.can_generate_videos && (
              <button
                onClick={() => setShowInstallModal(true)}
                className="cursor-pointer btn-primary flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                Install FFmpeg
              </button>
            )}
            <button
              onClick={handleRetryDetection}
              disabled={isRetrying}
              className="cursor-pointer btn-secondary flex items-center gap-2 disabled:opacity-60"
            >
              {isRetrying ? (
                <Loader2 className="w-4 h-4 animate-spin text-primary" />
              ) : (
                <RotateCcw className="w-4 h-4" />
              )}
              Retry Detection
            </button>
            <button
              onClick={handleResetPaths}
              disabled={isResetting}
              className="cursor-pointer btn-secondary flex items-center gap-2 disabled:opacity-60"
            >
              {isResetting ? (
                <Loader2 className="w-4 h-4 animate-spin text-primary" />
              ) : (
                <FolderOpen className="w-4 h-4" />
              )}
              Reset to Default
            </button>
          </div>

          <div className="border-t border-border-light dark:border-border-dark pt-4 space-y-3">
            <h4 className="text-sm font-medium">Custom Paths</h4>
            <div className="flex gap-3">
              <input
                type="text"
                placeholder="FFmpeg path (e.g., /usr/bin/ffmpeg)"
                value={ffmpegPath}
                onChange={(e) => setFfmpegPath(e.target.value)}
                className="input flex-1"
              />
              <button
                onClick={handleTestPath}
                disabled={isTesting}
                className="cursor-pointer btn-secondary flex items-center justify-center gap-2 disabled:opacity-60 min-w-24"
              >
                {isTesting ? (
                  <Loader2 className="w-4 h-4 animate-spin text-primary" />
                ) : (
                  <TestTube className="w-4 h-4" />
                )}
                Test
              </button>
            </div>
            <div className="flex gap-3">
              <input
                type="text"
                placeholder="FFprobe path (optional — auto-detected if omitted)"
                value={ffprobePath}
                onChange={(e) => setFfprobePath(e.target.value)}
                className="input flex-1"
              />
              <button
                onClick={handleSetPath}
                disabled={isSavingPath}
                className="cursor-pointer btn-primary flex items-center justify-center gap-2 disabled:opacity-60 min-w-24"
              >
                {isSavingPath ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <FolderInput className="w-4 h-4" />
                )}
                Save
              </button>
            </div>
          </div>
        </div>
      </SettingsSection>

      <SettingsSection title="Appearance" icon={Palette}>
        <div className="flex items-center gap-4">
          <button
            onClick={toggle}
            className={`cursor-pointer flex-1 p-4 rounded-xl border-2  ${
              !isDark
                ? "border-primary bg-primary/5"
                : "border-border-light dark:border-border-dark hover:bg-gray-50 dark:hover:bg-white/5"
            }`}
          >
            <Sun className="w-6 h-6 mx-auto mb-2 text-yellow-500" />
            <div className="text-sm font-medium">Light Mode</div>
            <div className="text-xs text-gray-500">Soft warm background</div>
          </button>
          <button
            onClick={toggle}
            className={`cursor-pointer flex-1 p-4 rounded-xl border-2  ${
              isDark
                ? "border-primary bg-primary/5"
                : "border-border-light dark:border-border-dark hover:bg-gray-50 dark:hover:bg-white/5"
            }`}
          >
            <Moon className="w-6 h-6 mx-auto mb-2 text-blue-400" />
            <div className="text-sm font-medium">Dark Mode</div>
            <div className="text-xs text-gray-500">Dark slate tones</div>
          </button>
        </div>
      </SettingsSection>

      {showInstallModal && (
        <FfmpegInstallModal onClose={() => setShowInstallModal(false)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Whisper model size inline component
// ---------------------------------------------------------------------------

function WhisperModelSizeSetting() {
  const [size, setSize] = useState("base");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    settingsApi
      .batchGet(["whisper_model_size"])
      .then(({ data }) => {
        if (data?.whisper_model_size) setSize(data.whisper_model_size);
      })
      .catch(() => {});
  }, []);

  const save = async (val: string) => {
    setSaving(true);
    try {
      await settingsApi.set("whisper_model_size", val);
      setSize(val);
      toast.success("Whisper model size saved");
    } catch {
      toast.error("Failed to save Whisper model size");
    } finally {
      setSaving(false);
    }
  };

  const options = [
    { value: "tiny",   label: "Tiny (~40MB, fastest, lower accuracy)" },
    { value: "base",   label: "Base (~150MB, recommended)" },
    { value: "small",  label: "Small (~470MB, better accuracy)" },
    { value: "medium", label: "Medium (~1.5GB, high accuracy)" },
  ];

  return (
    <div>
      <label className="block text-sm font-medium mb-1">
        Whisper Model Size
      </label>
      <div className="flex gap-3">
        <div className="relative flex-1">
          <select
            value={size}
            onChange={(e) => save(e.target.value)}
            disabled={saving}
            className="input w-full appearance-none pr-10"
          >
            {options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
        </div>
      </div>
      <p className="text-xs text-gray-500 mt-1">
        Larger models transcribe more accurately but take longer to load and run.
        Change takes effect on the next video generation.
      </p>
    </div>
  );
}
