import { ExternalLink } from "lucide-react";
import { settingsApi } from "@/services/api";
import toast from "react-hot-toast";

interface ApiKeyInputProps {
  label: string;
  placeholder: string;
  getUrl: string;
  settingKey: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
}

export function ApiKeyInput({
  label,
  placeholder,
  getUrl,
  settingKey,
  value,
  onChange,
  hint,
}: ApiKeyInputProps) {
  const handleSave = async () => {
    if (!value.trim()) {
      toast.error("Please enter an API key");
      return;
    }
    try {
      await settingsApi.set(settingKey, value, true);
      toast.success(`${label} API key saved securely`);
      onChange("");
    } catch (e) {
      toast.error("Failed to save API key");
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
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="font-medium">{label}</h4>
        <button
          onClick={() => openExternal(getUrl)}
          className="cursor-pointer text-sm text-primary flex items-center gap-1 hover:underline"
        >
          <ExternalLink className="w-3 h-3" />
          Get API Key
        </button>
      </div>
      <div className="flex gap-3">
        <input
          type="password"
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="input flex-1"
        />
        <button onClick={handleSave} className="cursor-pointer btn-primary">
          Save
        </button>
      </div>
      {hint && <p className="text-xs text-gray-500">{hint}</p>}
    </div>
  );
}
