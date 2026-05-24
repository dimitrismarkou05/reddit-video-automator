import { useState, useEffect } from "react";
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
  Volume2,
} from "lucide-react";
import { useThemeStore, useAuthStore } from "@/store";
import { SettingsSection } from "@/components/settings/SettingsSection";
import { FfmpegStatus } from "@/components/ffmpeg/FfmpegStatus";
import { FfmpegInstallModal } from "@/components/ffmpeg/FfmpegInstallModal";
import { ffmpegApi, ttsLocalApi, settingsApi } from "@/services/api";
import { useFfmpegStatus } from "@/hooks/useFfmpegStatus";
import { useTtsLocalStatus } from "@/hooks/useTtsLocalStatus";
import toast from "react-hot-toast";

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

  const [defaultVoice, setDefaultVoice] = useState("default");
  const [voices, setVoices] = useState<{ id: string; name: string }[]>([]);
  const [isInstallingTts, setIsInstallingTts] = useState(false);
  const [isRetryingTts, setIsRetryingTts] = useState(false);

  const { status: ffmpegStatus, refetch: refetchFfmpeg } = useFfmpegStatus();
  const { status: ttsStatus, refetch: refetchTts } = useTtsLocalStatus();

  useEffect(() => {
    if (ttsStatus?.voices) {
      setVoices(ttsStatus.voices);
    }
  }, [ttsStatus]);

  useEffect(() => {
    const loadDefaultVoice = async () => {
      try {
        const { data } = await settingsApi.get("default_tts_voice");
        if (data?.value) setDefaultVoice(data.value);
      } catch (e) {}
    };
    loadDefaultVoice();
  }, []);

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

  const handleInstallTts = async () => {
    setIsInstallingTts(true);
    try {
      await ttsLocalApi.install();
      toast.success("TTS model installation started");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to start TTS install");
      setIsInstallingTts(false);
    }
  };

  const handleRetryTts = async () => {
    setIsRetryingTts(true);
    try {
      await ttsLocalApi.retry();
      toast.success("Retrying TTS model installation");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Retry failed");
      setIsRetryingTts(false);
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

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold mb-6">Settings</h2>

      <SettingsSection title="Video Generation" icon={Volume2}>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">
              Default Voice
            </label>
            <div className="flex gap-3">
              <select
                value={defaultVoice}
                onChange={(e) => setDefaultVoice(e.target.value)}
                className="input flex-1"
                disabled={!ttsStatus?.installed}
              >
                {voices.length === 0 && (
                  <option value="default">No voices installed</option>
                )}
                {voices.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </select>
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
                Install a TTS model to enable voice selection.
              </p>
            )}
          </div>

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

          <div className="border-t border-border-light dark:border-border-dark pt-4">
            <h4 className="text-sm font-medium mb-2">TTS Model Status</h4>
            {ttsStatus?.installed ? (
              <div className="flex items-center gap-2 text-sm text-green-600 bg-green-50 dark:bg-green-900/20 p-3 rounded-lg">
                <Check className="w-4 h-4" />
                <span>
                  TTS model installed ({voices.length} voice
                  {voices.length !== 1 ? "s" : ""})
                </span>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex items-start gap-2 text-sm text-yellow-700 bg-yellow-50 dark:bg-yellow-900/20 p-3 rounded-lg">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>
                    TTS model not installed. Voice generation is disabled.
                  </span>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleInstallTts}
                    disabled={isInstallingTts}
                    className="cursor-pointer btn-primary flex items-center gap-2 disabled:opacity-50"
                  >
                    {isInstallingTts ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Download className="w-4 h-4" />
                    )}
                    Install TTS Model
                  </button>
                  <button
                    onClick={handleRetryTts}
                    disabled={isRetryingTts}
                    className="cursor-pointer btn-secondary flex items-center gap-2 disabled:opacity-50"
                  >
                    {isRetryingTts ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <RotateCcw className="w-4 h-4" />
                    )}
                    Retry
                  </button>
                </div>
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
