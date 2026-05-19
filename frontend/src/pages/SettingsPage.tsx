import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Key,
  Film,
  Palette,
  FolderOpen,
  ExternalLink,
  Check,
  AlertCircle,
  Sun,
  Moon,
  Monitor,
  Mic,
} from "lucide-react";
import { useThemeStore, useAuthStore } from "@/store";
import { SettingsSection } from "@/components/settings/SettingsSection";
import { ApiKeyInput } from "@/components/settings/ApiKeyInput";

export function SettingsPage() {
  const { isDark, toggle } = useThemeStore();
  const { authStatus } = useAuthStore();
  const [ttsKey, setTtsKey] = useState("");
  const [elevenLabsKey, setElevenLabsKey] = useState("");
  const [ffmpegPath, setFfmpegPath] = useState("");
  const [outputDir, setOutputDir] = useState("");

  const { data: ffmpegInfo } = useQuery({
    queryKey: ["ffmpeg"],
    queryFn: async () => {
      return {
        installed: true,
        path: "/usr/bin/ffmpeg",
        version: "ffmpeg version 6.0",
      };
    },
    staleTime: Infinity,
  });

  const handleSelectOutputDir = async () => {
    if (window.electronAPI) {
      const path = await window.electronAPI.selectDirectory();
      if (path) {
        setOutputDir(path);
      }
    }
  };

  const openExternal = async (url: string) => {
    if (window.electronAPI) {
      await window.electronAPI.openExternal(url);
    } else {
      window.open(url, "_blank");
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold mb-6">Settings</h2>

      <SettingsSection title="Text-to-Speech APIs" icon={Mic}>
        <ApiKeyInput
          label="OpenAI (Default)"
          placeholder="sk-..."
          getUrl="https://platform.openai.com/api-keys"
          settingKey="openai_api_key"
          value={ttsKey}
          onChange={setTtsKey}
          hint="Used for voice narration. Your key is encrypted at rest."
        />
        <div className="border-t border-border-light dark:border-border-dark pt-4 mt-4">
          <ApiKeyInput
            label="ElevenLabs (Optional)"
            placeholder="ElevenLabs API key..."
            getUrl="https://elevenlabs.io/app/settings/api-keys"
            settingKey="elevenlabs_api_key"
            value={elevenLabsKey}
            onChange={setElevenLabsKey}
            hint="Higher quality voices. Optional — falls back to OpenAI if not set."
          />
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

      <SettingsSection title="FFmpeg Settings" icon={Film}>
        {ffmpegInfo ? (
          <div className="space-y-3">
            <div className="flex items-center gap-3 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
              <Check className="w-5 h-5 text-green-500" />
              <div>
                <p className="font-medium text-sm">FFmpeg Detected</p>
                <p className="text-xs text-gray-500">{ffmpegInfo.path}</p>
              </div>
            </div>
            <p className="text-xs text-gray-500 font-mono">
              {ffmpegInfo.version}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-3 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
              <AlertCircle className="w-5 h-5 text-red-500" />
              <p className="text-sm">FFmpeg not detected on system</p>
            </div>
            <button
              onClick={() => openExternal("https://ffmpeg.org/download.html")}
              className="cursor-pointer btn-secondary text-sm flex items-center gap-2"
            >
              <ExternalLink className="w-4 h-4" />
              Download FFmpeg
            </button>
            <div className="flex gap-3">
              <input
                type="text"
                placeholder="Manual FFmpeg path"
                value={ffmpegPath}
                onChange={(e) => setFfmpegPath(e.target.value)}
                className="input flex-1"
              />
              <button className="cursor-pointer btn-primary">Set Path</button>
            </div>
          </div>
        )}
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

      <SettingsSection title="Output Settings" icon={FolderOpen}>
        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium mb-1">
              Output Directory
            </label>
            <div className="flex gap-3">
              <input
                type="text"
                value={outputDir}
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
        </div>
      </SettingsSection>
    </div>
  );
}
