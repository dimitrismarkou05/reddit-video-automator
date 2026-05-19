import { useState } from "react";
import { X, Film, Mic, Type, Image, Settings } from "lucide-react";
import { videoApi } from "@/services/api";
import type { Story, SubtitleStyle } from "@/types";
import toast from "react-hot-toast";

const TTS_VOICES = [
  { id: "alloy", name: "Alloy", provider: "openai" },
  { id: "echo", name: "Echo", provider: "openai" },
  { id: "fable", name: "Fable", provider: "openai" },
  { id: "onyx", name: "Onyx", provider: "openai" },
  { id: "nova", name: "Nova", provider: "openai" },
  { id: "shimmer", name: "Shimmer", provider: "openai" },
];

interface GenerateVideoModalProps {
  story: Story;
  onClose: () => void;
}

export function GenerateVideoModal({
  story,
  onClose,
}: GenerateVideoModalProps) {
  const [settings, setSettings] = useState({
    tts_provider: "openai",
    tts_voice: "alloy",
    background_source: "",
    video_format: "shorts" as "shorts" | "normal",
    include_updates: true,
    subtitle_position: "center" as "center" | "bottom" | "top",
    subtitle_size: 48,
    generate_hashtags: true,
  });
  const [isGenerating, setIsGenerating] = useState(false);

  const handleSelectBackground = async () => {
    if (window.electronAPI) {
      const path = await window.electronAPI.selectDirectory();
      if (path) {
        setSettings((s) => ({ ...s, background_source: path }));
      }
    } else {
      const input = document.createElement("input");
      input.type = "file";
      (input as any).webkitdirectory = true;
      input.onchange = (e: any) => {
        const files = e.target.files;
        if (files.length > 0) {
          setSettings((s) => ({ ...s, background_source: files[0].path }));
        }
      };
      input.click();
    }
  };

  const handleGenerate = async () => {
    if (!settings.background_source) {
      toast.error("Please select a background video or folder");
      return;
    }

    setIsGenerating(true);

    try {
      const subtitleStyle: SubtitleStyle = {
        position: settings.subtitle_position,
        font_size: settings.subtitle_size,
        font_color: "#FFFFFF",
        outline_color: "#000000",
        outline_width: 2,
        max_width_percent: 90,
      };

      await videoApi.generate({
        story_id: story.id,
        include_updates: settings.include_updates,
        tts_provider: settings.tts_provider,
        tts_voice: settings.tts_voice,
        background_source: settings.background_source,
        video_format: settings.video_format,
        subtitle_style: subtitleStyle,
        generate_hashtags: settings.generate_hashtags,
      });

      toast.success(
        "Video generation started! Check the Videos tab for progress.",
      );
      onClose();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Failed to start video generation",
      );
      setIsGenerating(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-surface-light dark:bg-surface-dark rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-xl">
        {/* Header */}
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
            disabled={isGenerating}
            className="cursor-pointer p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-white/5 "
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {isGenerating ? (
            <div className="text-center py-12">
              <div className="relative w-20 h-20 mx-auto mb-4">
                <div className="absolute inset-0 rounded-full border-4 border-primary/20" />
                <div className="absolute inset-0 rounded-full border-4 border-primary border-t-transparent animate-spin" />
                <Film className="absolute inset-0 m-auto w-8 h-8 text-primary" />
              </div>
              <h3 className="text-lg font-semibold mb-2">
                Generating Video...
              </h3>
              <p className="text-sm text-gray-500">
                This may take a few minutes. You can close this modal and check
                progress in the Videos tab.
              </p>
            </div>
          ) : (
            <>
              {/* TTS Settings */}
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                  <Mic className="w-4 h-4" />
                  Text-to-Speech
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">
                      Provider
                    </label>
                    <select
                      value={settings.tts_provider}
                      onChange={(e) =>
                        setSettings((s) => ({
                          ...s,
                          tts_provider: e.target.value,
                        }))
                      }
                      className="input"
                    >
                      <option value="openai">OpenAI</option>
                      <option value="elevenlabs">ElevenLabs</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">
                      Voice
                    </label>
                    <select
                      value={settings.tts_voice}
                      onChange={(e) =>
                        setSettings((s) => ({
                          ...s,
                          tts_voice: e.target.value,
                        }))
                      }
                      className="input"
                    >
                      {TTS_VOICES.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              {/* Background */}
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                  <Image className="w-4 h-4" />
                  Background Video
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={handleSelectBackground}
                    className="cursor-pointer btn-secondary flex items-center gap-2"
                  >
                    <Image className="w-4 h-4" />
                    Select Folder
                  </button>
                  {settings.background_source && (
                    <span className="text-sm text-gray-600 dark:text-gray-400 truncate flex-1">
                      {settings.background_source}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500">
                  Select a folder with video files. One will be picked randomly
                  for each generation.
                </p>
              </div>

              {/* Format */}
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
                    className={`cursor-pointer flex-1 p-3 rounded-lg border-2  ${
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
                    className={`cursor-pointer flex-1 p-3 rounded-lg border-2  ${
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

              {/* Subtitles */}
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

              {/* Options */}
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
            </>
          )}
        </div>

        {/* Footer */}
        {!isGenerating && (
          <div className="flex items-center justify-end gap-3 p-6 border-t border-border-light dark:border-border-dark">
            <button onClick={onClose} className="cursor-pointer btn-secondary">
              Cancel
            </button>
            <button
              onClick={handleGenerate}
              className="cursor-pointer btn-primary flex items-center gap-2"
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
