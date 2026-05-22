import { useState, useEffect } from "react";
import { ExternalLink, Eye, EyeOff } from "lucide-react";
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
  const [showKey, setShowKey] = useState(false);
  const [savedValue, setSavedValue] = useState("");
  const [hasSavedKey, setHasSavedKey] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  // Fetch existing key (decrypted) on mount
  useEffect(() => {
    const checkExisting = async () => {
      setIsLoading(true);
      try {
        const { data } = await settingsApi.get(settingKey, true); // decrypt=true
        if (data && data.value) {
          setSavedValue(data.value);
          setHasSavedKey(true);
        }
      } catch (e) {
        // Key doesn't exist yet, that's fine
      } finally {
        setIsLoading(false);
      }
    };
    checkExisting();
  }, [settingKey]);

  const handleSave = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!value.trim()) {
      toast.error("Please enter an API key");
      return;
    }
    try {
      await settingsApi.set(settingKey, value, true);
      toast.success(`${label} API key saved securely`);
      // Refresh to get the saved value
      const { data } = await settingsApi.get(settingKey, true);
      if (data && data.value) {
        setSavedValue(data.value);
        setHasSavedKey(true);
      }
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

  // Show the actual input value if user is typing, otherwise show saved value
  const displayValue = value || (showKey ? savedValue : savedValue.replace(/./g, "•"));

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
      <form onSubmit={handleSave} className="flex gap-3">
        <div className="relative flex-1">
          <input
            type={showKey ? "text" : "password"}
            placeholder={isLoading ? "Loading..." : hasSavedKey ? "••••••••••••••••••••••" : placeholder}
            value={displayValue}
            onChange={(e) => onChange(e.target.value)}
            disabled={isLoading}
            className="input w-full pr-10 disabled:opacity-50"
          />
          {hasSavedKey && !isLoading && (
            <button
              type="button"
              onClick={() => setShowKey(!showKey)}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-white/10 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
              title={showKey ? "Hide key" : "Show key"}
            >
              {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          )}
        </div>
        <button type="submit" className="cursor-pointer btn-primary" disabled={isLoading}>
          Save
        </button>
      </form>
      {hint && <p className="text-xs text-gray-500">{hint}</p>}
    </div>
  );
}
