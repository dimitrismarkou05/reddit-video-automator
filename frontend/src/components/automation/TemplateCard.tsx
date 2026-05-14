import { useState } from "react";
import {
  Bot,
  Play,
  Pause,
  Trash2,
  ChevronRight,
  Clock,
  CheckCircle,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import type { AutomationTemplate } from "@/types";

interface TemplateCardProps {
  template: AutomationTemplate;
  onToggle: () => void;
  onDelete: () => void;
  onRun: () => void;
}

export function TemplateCard({
  template,
  onToggle,
  onDelete,
  onRun,
}: TemplateCardProps) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className="card p-5">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div
            className={`w-10 h-10 rounded-xl flex items-center justify-center ${
              template.is_active
                ? "bg-green-100 dark:bg-green-900/30"
                : "bg-gray-100 dark:bg-gray-700"
            }`}
          >
            <Bot
              className={`w-5 h-5 ${template.is_active ? "text-green-600" : "text-gray-500"}`}
            />
          </div>
          <div>
            <h3 className="font-semibold">{template.name}</h3>
            <p className="text-xs text-gray-500">
              {template.description || "No description"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onToggle}
            className={`cursor-pointer p-2 rounded-lg transition-colors ${
              template.is_active
                ? "bg-green-100 dark:bg-green-900/30 text-green-600 hover:bg-green-200"
                : "bg-gray-100 dark:bg-gray-700 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-600"
            }`}
            title={template.is_active ? "Pause template" : "Activate template"}
          >
            {template.is_active ? (
              <Pause className="w-4 h-4" />
            ) : (
              <Play className="w-4 h-4" />
            )}
          </button>
          <button
            onClick={onRun}
            className="cursor-pointer p-2 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
            title="Run now"
          >
            <Play className="w-4 h-4" />
          </button>
          <button
            onClick={onDelete}
            className="cursor-pointer p-2 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
            title="Delete template"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mb-3">
        {template.subreddit_names.map((name) => (
          <span
            key={name}
            className="px-2 py-1 bg-primary/10 text-primary text-xs rounded-md font-medium"
          >
            r/{name}
          </span>
        ))}
        <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 text-xs rounded-md">
          {template.video_format === "shorts" ? "9:16" : "16:9"}
        </span>
        <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 text-xs rounded-md">
          {template.tts_provider}
        </span>
      </div>

      <div className="flex items-center justify-between text-xs text-gray-500">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {template.schedule_type === "manual" ? "Manual" : "Scheduled"}
          </span>
          {template.last_run_at && (
            <span className="flex items-center gap-1">
              <CheckCircle className="w-3 h-3" />
              Last run{" "}
              {formatDistanceToNow(new Date(template.last_run_at), {
                addSuffix: true,
              })}
            </span>
          )}
        </div>
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="cursor-pointer flex items-center gap-1 text-primary hover:underline"
        >
          {showDetails ? "Less" : "More"}
          <ChevronRight
            className={`w-3 h-3 transition-transform ${showDetails ? "rotate-90" : ""}`}
          />
        </button>
      </div>

      {showDetails && (
        <div className="mt-4 pt-4 border-t border-border-light dark:border-border-dark space-y-2 text-sm">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-gray-500">TTS Voice:</span>{" "}
              <span className="font-medium">{template.tts_voice}</span>
            </div>
            <div>
              <span className="text-gray-500">Auto-upload:</span>{" "}
              <span className="font-medium">
                {template.auto_upload ? "Yes" : "No"}
              </span>
            </div>
            <div>
              <span className="text-gray-500">Include Updates:</span>{" "}
              <span className="font-medium">
                {template.include_updates ? "Yes" : "No"}
              </span>
            </div>
            <div>
              <span className="text-gray-500">YouTube Privacy:</span>{" "}
              <span className="font-medium capitalize">
                {template.youtube_privacy}
              </span>
            </div>
          </div>
          {template.youtube_title_template && (
            <div>
              <span className="text-gray-500">Title Template:</span>{" "}
              <code className="text-xs bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">
                {template.youtube_title_template}
              </code>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
