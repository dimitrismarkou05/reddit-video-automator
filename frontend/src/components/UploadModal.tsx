import { useState } from "react";
import { X, Upload, Lock, Globe, Eye } from "lucide-react";
import { youtubeApi } from "@/services/api";
import type { GeneratedVideo } from "@/types";
import toast from "react-hot-toast";

interface UploadModalProps {
  video: GeneratedVideo;
  onClose: () => void;
}

const PRIVACY_OPTIONS = [
  {
    value: "private",
    label: "Private",
    icon: Lock,
    description: "Only you can see",
  },
  {
    value: "unlisted",
    label: "Unlisted",
    icon: Eye,
    description: "Anyone with link",
  },
  {
    value: "public",
    label: "Public",
    icon: Globe,
    description: "Everyone can see",
  },
];

const CATEGORIES = [
  { id: "22", name: "People & Blogs" },
  { id: "24", name: "Entertainment" },
  { id: "27", name: "Education" },
  { id: "28", name: "Science & Tech" },
  { id: "20", name: "Gaming" },
  { id: "1", name: "Film & Animation" },
];

export function UploadModal({ video, onClose }: UploadModalProps) {
  const [form, setForm] = useState({
    title: video.story?.title || "",
    description: "",
    tags: "",
    privacy: "private",
    category: "22",
    uploadThumbnail: true,
  });
  const [isUploading, setIsUploading] = useState(false);

  const handleSubmit = async () => {
    setIsUploading(true);

    try {
      await youtubeApi.upload({
        video_id: video.id,
        title: form.title,
        description: form.description,
        tags: form.tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        privacy_status: form.privacy,
        category_id: form.category,
        upload_thumbnail: form.uploadThumbnail,
      });

      toast.success("Upload started! Check the Videos tab for progress.");
      onClose();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Upload failed");
      setIsUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-surface-light dark:bg-surface-dark rounded-2xl w-full max-w-lg shadow-xl">
        <div className="flex items-center justify-between p-6 border-b border-border-light dark:border-border-dark">
          <h2 className="text-lg font-semibold">Upload to YouTube</h2>
          <button
            onClick={onClose}
            className="cursor-pointer p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-white/5 "
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {isUploading ? (
            <div className="text-center py-8">
              <div className="relative w-16 h-16 mx-auto mb-4">
                <Upload className="w-8 h-8 text-primary absolute inset-0 m-auto" />
                <svg className="w-16 h-16 animate-spin" viewBox="0 0 50 50">
                  <circle
                    cx="25"
                    cy="25"
                    r="20"
                    fill="none"
                    stroke="#e5e7eb"
                    strokeWidth="4"
                  />
                  <circle
                    cx="25"
                    cy="25"
                    r="20"
                    fill="none"
                    stroke="#ff4500"
                    strokeWidth="4"
                    strokeDasharray="80"
                    strokeDashoffset="60"
                  />
                </svg>
              </div>
              <p className="text-sm text-gray-500">Uploading to YouTube...</p>
            </div>
          ) : (
            <>
              <div>
                <label className="block text-sm font-medium mb-1">Title</label>
                <input
                  type="text"
                  value={form.title}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, title: e.target.value }))
                  }
                  className="input"
                  maxLength={100}
                />
                <p className="text-xs text-gray-500 mt-1">
                  {form.title.length}/100
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">
                  Description
                </label>
                <textarea
                  value={form.description}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, description: e.target.value }))
                  }
                  className="input h-24 resize-none"
                  placeholder="Video description..."
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">
                  Tags (comma separated)
                </label>
                <input
                  type="text"
                  value={form.tags}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, tags: e.target.value }))
                  }
                  className="input"
                  placeholder="reddit, story, viral"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Privacy
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {PRIVACY_OPTIONS.map((opt) => {
                    const Icon = opt.icon;
                    return (
                      <button
                        key={opt.value}
                        onClick={() =>
                          setForm((f) => ({ ...f, privacy: opt.value }))
                        }
                        className={`cursor-pointer p-3 rounded-lg border-2 text-center  ${
                          form.privacy === opt.value
                            ? "border-primary bg-primary/5"
                            : "border-border-light dark:border-border-dark hover:bg-gray-50 dark:hover:bg-white/5"
                        }`}
                      >
                        <Icon className="w-5 h-5 mx-auto mb-1" />
                        <div className="text-sm font-medium">{opt.label}</div>
                        <div className="text-xs text-gray-500">
                          {opt.description}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">
                  Category
                </label>
                <select
                  value={form.category}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, category: e.target.value }))
                  }
                  className="input"
                >
                  {CATEGORIES.map((cat) => (
                    <option key={cat.id} value={cat.id}>
                      {cat.name}
                    </option>
                  ))}
                </select>
              </div>

              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.uploadThumbnail}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      uploadThumbnail: e.target.checked,
                    }))
                  }
                  className="w-4 h-4 rounded text-primary"
                />
                <span className="text-sm">Upload custom thumbnail</span>
              </label>
            </>
          )}
        </div>

        {!isUploading && (
          <div className="flex items-center justify-end gap-3 p-6 border-t border-border-light dark:border-border-dark">
            <button onClick={onClose} className="cursor-pointer btn-secondary">
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              className="cursor-pointer btn-primary flex items-center gap-2"
            >
              <Upload className="w-4 h-4" />
              Upload Now
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
