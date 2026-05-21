import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, Plus, AlertTriangle } from "lucide-react";
import { automationApi } from "@/services/api";
import type { AutomationTemplate } from "@/types";
import { TemplateCard } from "@/components/automation/TemplateCard";
import { CreateTemplateModal } from "@/components/automation/CreateTemplateModal";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadingSpinner } from "@/components/common/LoadingSpinner";
import { PageHeader } from "@/components/common/PageHeader";
import { useFfmpegStatus } from "@/hooks/useFfmpegStatus";
import toast from "react-hot-toast";

export function AutomationPage() {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const { status: ffmpegStatus } = useFfmpegStatus();
  const canGenerate = ffmpegStatus?.can_generate_videos ?? false;

  const {
    data: templates,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["templates"],
    queryFn: async () => {
      const { data } = await automationApi.listTemplates();
      return data;
    },
  });

  const handleToggle = async (id: number) => {
    try {
      await automationApi.toggleTemplate(id);
      toast.success("Template status updated");
      refetch();
    } catch (e) {
      toast.error("Failed to toggle template");
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this automation template?")) return;
    try {
      await automationApi.deleteTemplate(id);
      toast.success("Template deleted");
      refetch();
    } catch (e) {
      toast.error("Failed to delete template");
    }
  };

  const handleRun = async (id: number) => {
    if (!canGenerate) {
      toast.error("FFmpeg not installed. Please install FFmpeg in Settings to generate videos.");
      return;
    }
    try {
      await automationApi.runTemplate(id);
      toast.success("Template run queued");
    } catch (e) {
      toast.error("Failed to run template");
    }
  };

  const handleCreateClick = () => {
    if (!canGenerate) {
      toast.error("FFmpeg not installed. Please install FFmpeg in Settings before creating templates.");
      return;
    }
    setShowCreateModal(true);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Automation Templates"
        subtitle="Create workflows that automatically fetch, generate, and upload videos"
        actions={
          <button
            onClick={handleCreateClick}
            className={`cursor-pointer btn-primary flex items-center gap-2 ${
              !canGenerate ? "opacity-60" : ""
            }`}
          >
            <Plus className="w-4 h-4" />
            New Template
          </button>
        }
      />

      {/* FFmpeg missing warning */}
      {!canGenerate && (
        <div className="flex items-center gap-3 p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-xl">
          <AlertTriangle className="w-5 h-5 text-yellow-600 dark:text-yellow-400 shrink-0" />
          <div>
            <p className="text-sm font-medium text-yellow-700 dark:text-yellow-300">
              FFmpeg Not Installed
            </p>
            <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-0.5">
              Video generation is disabled. Templates can be created but will not generate videos until FFmpeg is installed.
            </p>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <LoadingSpinner size="md" />
        </div>
      ) : templates && templates.length > 0 ? (
        <div className="space-y-4">
          {templates.map((template: AutomationTemplate) => (
            <TemplateCard
              key={template.id}
              template={template}
              onToggle={() => handleToggle(template.id)}
              onDelete={() => handleDelete(template.id)}
              onRun={() => handleRun(template.id)}
              canGenerate={canGenerate}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={Bot}
          title="No templates yet"
          subtitle="Create your first automation template to start auto-publishing"
        />
      )}

      {showCreateModal && (
        <CreateTemplateModal
          onClose={() => setShowCreateModal(false)}
          onCreated={refetch}
        />
      )}
    </div>
  );
}
