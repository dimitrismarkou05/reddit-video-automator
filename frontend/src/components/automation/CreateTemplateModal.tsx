import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { XCircle, Plus } from "lucide-react";
import { ModalHeader } from "@/components/common/ModalHeader";
import { ModalFooter } from "@/components/common/ModalFooter";
import { ModalShell } from "@/components/common/ModalShell";
import { automationApi, ttsLocalApi } from "@/services/api";
import toast from "react-hot-toast";

interface CreateTemplateModalProps {
  onClose: () => void;
  onCreated: () => void;
}

export function CreateTemplateModal({
  onClose,
  onCreated,
}: CreateTemplateModalProps) {
  const [form, setForm] = useState({
    name: "",
    description: "",
    subreddit_names: "",
    voice_id: "en_ljspeech_vits",
    background_source: "",
    video_format: "shorts",
    include_updates: true,
    generate_hashtags: true,
    youtube_privacy: "private",
    auto_upload: true,
    schedule_type: "manual",
  });
  const [isCreating, setIsCreating] = useState(false);

  const { data: voices } = useQuery({
    queryKey: ["tts-voices"],
    queryFn: async () => {
      const { data } = await ttsLocalApi.listVoices();
      return data as { id: string; name: string }[];
    },
    staleTime: 60000,
  });

  const handleSubmit = async () => {
    if (!form.name.trim() || !form.subreddit_names.trim()) {
      toast.error("Name and subreddits are required");
      return;
    }

    setIsCreating(true);
    try {
      await automationApi.createTemplate({
        ...form,
        subreddit_names: form.subreddit_names
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      toast.success("Template created successfully");
      onCreated();
      onClose();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Failed to create template");
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <ModalShell onClose={onClose} maxWidth="max-w-lg">
      <ModalHeader
        title="Create Automation Template"
        icon={XCircle}
        onClose={onClose}
      />

      <div className="p-6 space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">
            Template Name
          </label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            className="input"
            placeholder="e.g., Daily Reddit Stories"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Description</label>
          <textarea
            value={form.description}
            onChange={(e) =>
              setForm((f) => ({ ...f, description: e.target.value }))
            }
            className="input h-16 resize-none"
            placeholder="What this template does..."
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">
            Subreddits (comma separated)
          </label>
          <input
            type="text"
            value={form.subreddit_names}
            onChange={(e) =>
              setForm((f) => ({ ...f, subreddit_names: e.target.value }))
            }
            className="input"
            placeholder="AskReddit, TIFU, relationships"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">TTS Voice</label>
          <select
            value={form.voice_id}
            onChange={(e) =>
              setForm((f) => ({ ...f, voice_id: e.target.value }))
            }
            className="input"
            disabled={!voices?.length}
          >
            {voices?.map((voice) => (
              <option key={voice.id} value={voice.id}>
                {voice.name}
              </option>
            )) ?? (
              <option value={form.voice_id}>Loading voices...</option>
            )}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">
            Background Video Folder
          </label>
          <input
            type="text"
            value={form.background_source}
            onChange={(e) =>
              setForm((f) => ({ ...f, background_source: e.target.value }))
            }
            className="input"
            placeholder="Path to background videos folder"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium mb-1">Format</label>
            <select
              value={form.video_format}
              onChange={(e) =>
                setForm((f) => ({ ...f, video_format: e.target.value }))
              }
              className="input"
            >
              <option value="shorts">Shorts (9:16)</option>
              <option value="normal">Normal (16:9)</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">
              YouTube Privacy
            </label>
            <select
              value={form.youtube_privacy}
              onChange={(e) =>
                setForm((f) => ({ ...f, youtube_privacy: e.target.value }))
              }
              className="input"
            >
              <option value="private">Private</option>
              <option value="unlisted">Unlisted</option>
              <option value="public">Public</option>
            </select>
          </div>
        </div>

        <div className="flex gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.include_updates}
              onChange={(e) =>
                setForm((f) => ({ ...f, include_updates: e.target.checked }))
              }
              className="w-4 h-4 rounded text-primary"
            />
            <span className="text-sm">Include updates</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.auto_upload}
              onChange={(e) =>
                setForm((f) => ({ ...f, auto_upload: e.target.checked }))
              }
              className="w-4 h-4 rounded text-primary"
            />
            <span className="text-sm">Auto-upload</span>
          </label>
        </div>
      </div>

      <ModalFooter>
        <button onClick={onClose} className="btn-secondary">
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={isCreating}
          className="cursor-pointer btn-primary flex items-center gap-2"
        >
          {isCreating ? (
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
          ) : (
            <Plus className="w-4 h-4" />
          )}
          Create Template
        </button>
      </ModalFooter>
    </ModalShell>
  );
}
