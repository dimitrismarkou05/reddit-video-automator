import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { 
  Bot, Plus, Play, Pause, Trash2, ChevronRight, Clock, CheckCircle, 
  XCircle, AlertCircle, Film, BarChart3
} from 'lucide-react';
import { automationApi } from '@/services/api';
import type { AutomationTemplate } from '@/types';
import { formatDistanceToNow } from 'date-fns';
import toast from 'react-hot-toast';

function TemplateCard({ template, onToggle, onDelete, onRun }: { 
  template: AutomationTemplate; 
  onToggle: () => void;
  onDelete: () => void;
  onRun: () => void;
}) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className="card p-5">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
            template.is_active ? 'bg-green-100 dark:bg-green-900/30' : 'bg-gray-100 dark:bg-gray-700'
          }`}>
            <Bot className={`w-5 h-5 ${template.is_active ? 'text-green-600' : 'text-gray-500'}`} />
          </div>
          <div>
            <h3 className="font-semibold">{template.name}</h3>
            <p className="text-xs text-gray-500">{template.description || 'No description'}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onToggle}
            className={`p-2 rounded-lg transition-colors ${
              template.is_active
                ? 'bg-green-100 dark:bg-green-900/30 text-green-600 hover:bg-green-200'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-600'
            }`}
            title={template.is_active ? 'Pause template' : 'Activate template'}
          >
            {template.is_active ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
          </button>
          <button
            onClick={onRun}
            className="p-2 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
            title="Run now"
          >
            <Play className="w-4 h-4" />
          </button>
          <button
            onClick={onDelete}
            className="p-2 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
            title="Delete template"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mb-3">
        {template.subreddit_names.map((name) => (
          <span key={name} className="px-2 py-1 bg-primary/10 text-primary text-xs rounded-md font-medium">
            r/{name}
          </span>
        ))}
        <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 text-xs rounded-md">
          {template.video_format === 'shorts' ? '9:16' : '16:9'}
        </span>
        <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 text-xs rounded-md">
          {template.tts_provider}
        </span>
      </div>

      <div className="flex items-center justify-between text-xs text-gray-500">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {template.schedule_type === 'manual' ? 'Manual' : 'Scheduled'}
          </span>
          {template.last_run_at && (
            <span className="flex items-center gap-1">
              <CheckCircle className="w-3 h-3" />
              Last run {formatDistanceToNow(new Date(template.last_run_at), { addSuffix: true })}
            </span>
          )}
        </div>
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="flex items-center gap-1 text-primary hover:underline"
        >
          {showDetails ? 'Less' : 'More'}
          <ChevronRight className={`w-3 h-3 transition-transform ${showDetails ? 'rotate-90' : ''}`} />
        </button>
      </div>

      {showDetails && (
        <div className="mt-4 pt-4 border-t border-border-light dark:border-border-dark space-y-2 text-sm">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-gray-500">TTS Voice:</span>{' '}
              <span className="font-medium">{template.tts_voice}</span>
            </div>
            <div>
              <span className="text-gray-500">Auto-upload:</span>{' '}
              <span className="font-medium">{template.auto_upload ? 'Yes' : 'No'}</span>
            </div>
            <div>
              <span className="text-gray-500">Include Updates:</span>{' '}
              <span className="font-medium">{template.include_updates ? 'Yes' : 'No'}</span>
            </div>
            <div>
              <span className="text-gray-500">YouTube Privacy:</span>{' '}
              <span className="font-medium capitalize">{template.youtube_privacy}</span>
            </div>
          </div>
          {template.youtube_title_template && (
            <div>
              <span className="text-gray-500">Title Template:</span>{' '}
              <code className="text-xs bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">{template.youtube_title_template}</code>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function AutomationPage() {
  const [showCreateModal, setShowCreateModal] = useState(false);

  const { data: templates, isLoading, refetch } = useQuery({
    queryKey: ['templates'],
    queryFn: async () => {
      const { data } = await automationApi.listTemplates();
      return data;
    },
  });

  const handleToggle = async (id: number) => {
    try {
      await automationApi.toggleTemplate(id);
      toast.success('Template status updated');
      refetch();
    } catch (e) {
      toast.error('Failed to toggle template');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this automation template?')) return;
    try {
      await automationApi.deleteTemplate(id);
      toast.success('Template deleted');
      refetch();
    } catch (e) {
      toast.error('Failed to delete template');
    }
  };

  const handleRun = async (id: number) => {
    try {
      await automationApi.runTemplate(id);
      toast.success('Template run queued');
    } catch (e) {
      toast.error('Failed to run template');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Automation Templates</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Create workflows that automatically fetch, generate, and upload videos
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="btn-primary flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          New Template
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
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
        <div className="card p-12 text-center">
          <Bot className="w-12 h-12 mx-auto mb-4 text-gray-300" />
          <h3 className="text-lg font-semibold text-gray-500">No templates yet</h3>
          <p className="text-sm text-gray-400 mt-1">
            Create your first automation template to start auto-publishing
          </p>
        </div>
      )}

      {showCreateModal && (
        <CreateTemplateModal onClose={() => setShowCreateModal(false)} onCreated={refetch} />
      )}
    </div>
  );
}

function CreateTemplateModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState({
    name: '',
    description: '',
    subreddit_names: '',
    tts_provider: 'openai',
    tts_voice: 'alloy',
    background_source: '',
    video_format: 'shorts',
    include_updates: true,
    generate_hashtags: true,
    youtube_privacy: 'private',
    auto_upload: true,
    schedule_type: 'manual',
  });
  const [isCreating, setIsCreating] = useState(false);

  const handleSubmit = async () => {
    if (!form.name.trim() || !form.subreddit_names.trim()) {
      toast.error('Name and subreddits are required');
      return;
    }

    setIsCreating(true);
    try {
      await automationApi.createTemplate({
        ...form,
        subreddit_names: form.subreddit_names.split(',').map((s) => s.trim()).filter(Boolean),
      });
      toast.success('Template created successfully');
      onCreated();
      onClose();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Failed to create template');
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-surface-light dark:bg-surface-dark rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-xl">
        <div className="flex items-center justify-between p-6 border-b border-border-light dark:border-border-dark">
          <h2 className="text-lg font-semibold">Create Automation Template</h2>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
            <XCircle className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Template Name</label>
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
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              className="input h-16 resize-none"
              placeholder="What this template does..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Subreddits (comma separated)</label>
            <input
              type="text"
              value={form.subreddit_names}
              onChange={(e) => setForm((f) => ({ ...f, subreddit_names: e.target.value }))}
              className="input"
              placeholder="AskReddit, TIFU, relationships"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1">TTS Provider</label>
              <select
                value={form.tts_provider}
                onChange={(e) => setForm((f) => ({ ...f, tts_provider: e.target.value }))}
                className="input"
              >
                <option value="openai">OpenAI</option>
                <option value="elevenlabs">ElevenLabs</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Voice</label>
              <select
                value={form.tts_voice}
                onChange={(e) => setForm((f) => ({ ...f, tts_voice: e.target.value }))}
                className="input"
              >
                <option value="alloy">Alloy</option>
                <option value="echo">Echo</option>
                <option value="fable">Fable</option>
                <option value="onyx">Onyx</option>
                <option value="nova">Nova</option>
                <option value="shimmer">Shimmer</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Background Video Folder</label>
            <input
              type="text"
              value={form.background_source}
              onChange={(e) => setForm((f) => ({ ...f, background_source: e.target.value }))}
              className="input"
              placeholder="Path to background videos folder"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1">Format</label>
              <select
                value={form.video_format}
                onChange={(e) => setForm((f) => ({ ...f, video_format: e.target.value }))}
                className="input"
              >
                <option value="shorts">Shorts (9:16)</option>
                <option value="normal">Normal (16:9)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">YouTube Privacy</label>
              <select
                value={form.youtube_privacy}
                onChange={(e) => setForm((f) => ({ ...f, youtube_privacy: e.target.value }))}
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
                onChange={(e) => setForm((f) => ({ ...f, include_updates: e.target.checked }))}
                className="w-4 h-4 rounded text-primary"
              />
              <span className="text-sm">Include updates</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.auto_upload}
                onChange={(e) => setForm((f) => ({ ...f, auto_upload: e.target.checked }))}
                className="w-4 h-4 rounded text-primary"
              />
              <span className="text-sm">Auto-upload</span>
            </label>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 p-6 border-t border-border-light dark:border-border-dark">
          <button onClick={onClose} className="btn-secondary">Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={isCreating}
            className="btn-primary flex items-center gap-2"
          >
            {isCreating ? (
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            Create Template
          </button>
        </div>
      </div>
    </div>
  );
}
