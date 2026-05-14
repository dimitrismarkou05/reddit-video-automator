import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, Plus } from "lucide-react";
import { automationApi } from "@/services/api";
import type { AutomationTemplate } from "@/types";
import { TemplateCard } from "@/components/automation/TemplateCard";
import { CreateTemplateModal } from "@/components/automation/CreateTemplateModal";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadingSpinner } from "@/components/common/LoadingSpinner";
import { PageHeader } from "@/components/common/PageHeader";
import toast from "react-hot-toast";

export function AutomationPage() {
  const [showCreateModal, setShowCreateModal] = useState(false);

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
    try {
      await automationApi.runTemplate(id);
      toast.success("Template run queued");
    } catch (e) {
      toast.error("Failed to run template");
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Automation Templates"
        subtitle="Create workflows that automatically fetch, generate, and upload videos"
        actions={
          <button
            onClick={() => setShowCreateModal(true)}
            className="cursor-pointer btn-primary flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            New Template
          </button>
        }
      />

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
