import React, { useState, useEffect } from 'react';
import { X, Eye, ThumbsUp, MessageSquare, Clock, Globe, Lock, EyeOff, Save, Trash2, AlertCircle } from 'lucide-react';
import { youtubeApi } from '@/services/api';
import type { VideoStats } from '@/types';
import toast from 'react-hot-toast';

interface StatsModalProps {
  videoId: string;
  onClose: () => void;
}

export function StatsModal({ videoId, onClose }: StatsModalProps) {
  const [stats, setStats] = useState<VideoStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({ title: '', description: '', tags: '' });
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const { data } = await youtubeApi.getStats(videoId);
        setStats(data);
        setEditForm({
          title: data.title,
          description: data.description,
          tags: data.tags.join(', '),
        });
      } catch (e: any) {
        toast.error('Failed to load video statistics');
      } finally {
        setIsLoading(false);
      }
    };
    fetchStats();
  }, [videoId]);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await youtubeApi.updateMetadata(videoId, {
        title: editForm.title,
        description: editForm.description,
        tags: editForm.tags.split(',').map((t) => t.trim()).filter(Boolean),
      });
      toast.success('Metadata updated successfully');
      setIsEditing(false);
      const { data } = await youtubeApi.getStats(videoId);
      setStats(data);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Failed to update metadata');
    } finally {
      setIsSaving(false);
    }
  };

  const handlePrivacyChange = async (privacy: string) => {
    try {
      await youtubeApi.updatePrivacy(videoId, privacy);
      toast.success(`Privacy changed to ${privacy}`);
      const { data } = await youtubeApi.getStats(videoId);
      setStats(data);
    } catch (e: any) {
      toast.error('Failed to change privacy');
    }
  };

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to permanently delete this video from YouTube?')) return;
    try {
      await youtubeApi.delete(videoId);
      toast.success('Video deleted from YouTube');
      onClose();
    } catch (e: any) {
      toast.error('Failed to delete video');
    }
  };

  if (isLoading) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div className="bg-surface-light dark:bg-surface-dark rounded-2xl p-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto" />
        </div>
      </div>
    );
  }

  if (!stats) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-surface-light dark:bg-surface-dark rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-xl">
        <div className="flex items-center justify-between p-6 border-b border-border-light dark:border-border-dark">
          <h2 className="text-lg font-semibold">YouTube Studio</h2>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Thumbnail */}
          {stats.thumbnail_url && (
            <div className="aspect-video rounded-xl overflow-hidden bg-gray-900">
              <img src={stats.thumbnail_url} alt="Thumbnail" className="w-full h-full object-cover" />
            </div>
          )}

          {/* Stats Grid */}
          <div className="grid grid-cols-3 gap-4">
            <div className="card p-4 text-center">
              <Eye className="w-6 h-6 mx-auto mb-2 text-blue-500" />
              <div className="text-2xl font-bold">{stats.views.toLocaleString()}</div>
              <div className="text-xs text-gray-500">Views</div>
            </div>
            <div className="card p-4 text-center">
              <ThumbsUp className="w-6 h-6 mx-auto mb-2 text-green-500" />
              <div className="text-2xl font-bold">{stats.likes.toLocaleString()}</div>
              <div className="text-xs text-gray-500">Likes</div>
            </div>
            <div className="card p-4 text-center">
              <MessageSquare className="w-6 h-6 mx-auto mb-2 text-purple-500" />
              <div className="text-2xl font-bold">{stats.comments.toLocaleString()}</div>
              <div className="text-xs text-gray-500">Comments</div>
            </div>
          </div>

          {/* Metadata */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">Video Details</h3>
              <button
                onClick={() => setIsEditing(!isEditing)}
                className="text-sm text-primary hover:text-primary-dark"
              >
                {isEditing ? 'Cancel' : 'Edit'}
              </button>
            </div>

            {isEditing ? (
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium mb-1">Title</label>
                  <input
                    type="text"
                    value={editForm.title}
                    onChange={(e) => setEditForm((f) => ({ ...f, title: e.target.value }))}
                    className="input"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Description</label>
                  <textarea
                    value={editForm.description}
                    onChange={(e) => setEditForm((f) => ({ ...f, description: e.target.value }))}
                    className="input h-24 resize-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Tags</label>
                  <input
                    type="text"
                    value={editForm.tags}
                    onChange={(e) => setEditForm((f) => ({ ...f, tags: e.target.value }))}
                    className="input"
                  />
                </div>
                <button
                  onClick={handleSave}
                  disabled={isSaving}
                  className="btn-primary flex items-center gap-2"
                >
                  <Save className="w-4 h-4" />
                  {isSaving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex items-start gap-2">
                  <span className="text-sm text-gray-500 w-24 flex-shrink-0">Title:</span>
                  <span className="text-sm font-medium">{stats.title}</span>
                </div>
                <div className="flex items-start gap-2">
                  <span className="text-sm text-gray-500 w-24 flex-shrink-0">Description:</span>
                  <span className="text-sm">{stats.description || 'No description'}</span>
                </div>
                <div className="flex items-start gap-2">
                  <span className="text-sm text-gray-500 w-24 flex-shrink-0">Tags:</span>
                  <div className="flex flex-wrap gap-1">
                    {stats.tags.map((tag) => (
                      <span key={tag} className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 rounded text-xs">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-500 w-24">Duration:</span>
                  <span className="text-sm">{stats.duration}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-500 w-24">Uploaded:</span>
                  <span className="text-sm">{new Date(stats.upload_date).toLocaleDateString()}</span>
                </div>
              </div>
            )}
          </div>

          {/* Privacy Controls */}
          <div className="space-y-3">
            <h3 className="font-semibold">Privacy Settings</h3>
            <div className="flex gap-2">
              {['private', 'unlisted', 'public'].map((privacy) => {
                const isActive = stats.privacy_status === privacy;
                return (
                  <button
                    key={privacy}
                    onClick={() => handlePrivacyChange(privacy)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition-colors ${
                      isActive
                        ? 'bg-primary text-white'
                        : 'bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }`}
                  >
                    {privacy}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Danger Zone */}
          <div className="border-t border-red-200 dark:border-red-800 pt-4">
            <button
              onClick={handleDelete}
              className="flex items-center gap-2 px-4 py-2 bg-red-50 dark:bg-red-900/20 text-red-600 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Delete from YouTube
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
