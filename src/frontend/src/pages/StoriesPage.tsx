import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { 
  Plus, RefreshCw, Link2, Film, ChevronDown, ChevronRight, 
  MessageCircle, ArrowUp, Calendar, ExternalLink, AlertCircle,
  BookOpen
} from 'lucide-react';
import { storyApi, subredditApi } from '@/services/api';
import { GenerateVideoModal } from '@/components/GenerateVideoModal';
import type { Story } from '@/types';
import { formatDistanceToNow } from 'date-fns';
import toast from 'react-hot-toast';

function StoryCard({ story, depth = 0 }: { story: Story; depth?: number }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const hasUpdates = story.updates && story.updates.length > 0;
  const hasVideo = !!story.generated_video;

  return (
    <div className={`${depth > 0 ? 'ml-8 border-l-2 border-primary/20 pl-4' : ''}`}>
      <div className="card p-4 mb-3 hover:shadow-md transition-shadow">
        <div className="flex items-start gap-4">
          {/* Expand button for updates */}
          {hasUpdates && (
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="mt-1 p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
            </button>
          )}

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2 py-0.5 bg-primary/10 text-primary text-xs rounded-full font-medium">
                r/{story.subreddit}
              </span>
              {story.is_update && (
                <span className="px-2 py-0.5 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 text-xs rounded-full font-medium">
                  Update
                </span>
              )}
              {hasVideo && (
                <span className="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 text-xs rounded-full font-medium flex items-center gap-1">
                  <Film className="w-3 h-3" />
                  Video Ready
                </span>
              )}
            </div>

            <h3 className="font-semibold text-base mb-1">{story.title}</h3>

            <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
              <span className="flex items-center gap-1">
                <ArrowUp className="w-3 h-3" />
                {story.score.toLocaleString()}
              </span>
              <span className="flex items-center gap-1">
                <MessageCircle className="w-3 h-3" />
                u/{story.author}
              </span>
              <span className="flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                {formatDistanceToNow(new Date(story.fetched_at), { addSuffix: true })}
              </span>
              {hasUpdates && (
                <span className="flex items-center gap-1 text-primary">
                  <Link2 className="w-3 h-3" />
                  {story.updates?.length} update{story.updates?.length !== 1 ? 's' : ''}
                </span>
              )}
            </div>

            {story.body && (
              <p className="mt-2 text-sm text-gray-600 dark:text-gray-300 line-clamp-2">
                {story.body.substring(0, 200)}
                {story.body.length > 200 ? '...' : ''}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <button
              onClick={() => setShowGenerateModal(true)}
              disabled={hasVideo}
              className={`p-2 rounded-lg transition-colors ${
                hasVideo
                  ? 'bg-green-100 dark:bg-green-900/30 text-green-600 cursor-default'
                  : 'bg-primary/10 text-primary hover:bg-primary/20'
              }`}
              title={hasVideo ? 'Video already generated' : 'Generate video'}
            >
              <Film className="w-5 h-5" />
            </button>
            <a
              href={story.permalink}
              target="_blank"
              rel="noopener noreferrer"
              className="p-2 rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
              title="View on Reddit"
            >
              <ExternalLink className="w-5 h-5" />
            </a>
          </div>
        </div>
      </div>

      {/* Nested updates */}
      {isExpanded && hasUpdates && (
        <div className="space-y-2">
          {story.updates?.map((update) => (
            <StoryCard key={update.id} story={update} depth={depth + 1} />
          ))}
        </div>
      )}

      {showGenerateModal && (
        <GenerateVideoModal
          story={story}
          onClose={() => setShowGenerateModal(false)}
        />
      )}
    </div>
  );
}

export function StoriesPage() {
  const [newSubreddit, setNewSubreddit] = useState('');
  const [isAdding, setIsAdding] = useState(false);

  const { data: stories, isLoading, refetch } = useQuery({
    queryKey: ['stories'],
    queryFn: async () => {
      const { data } = await storyApi.list();
      return data.filter((s: Story) => !s.is_update);
    },
  });

  const { data: subreddits } = useQuery({
    queryKey: ['subreddits'],
    queryFn: async () => {
      const { data } = await subredditApi.list();
      return data;
    },
  });

  const handleAddSubreddit = async () => {
    if (!newSubreddit.trim()) return;
    setIsAdding(true);
    try {
      await subredditApi.add(newSubreddit.trim());
      toast.success(`Added r/${newSubreddit.trim()}`);
      setNewSubreddit('');
      refetch();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Failed to add subreddit');
    } finally {
      setIsAdding(false);
    }
  };

  const handleFetchAll = async () => {
    try {
      toast.loading('Fetching stories...', { id: 'fetch' });
      await subredditApi.fetchAll();
      toast.success('Fetch complete!', { id: 'fetch' });
      refetch();
    } catch (e) {
      toast.error('Fetch failed', { id: 'fetch' });
    }
  };

  const handleLinkUpdates = async () => {
    try {
      toast.loading('Linking updates...', { id: 'link' });
      await storyApi.linkUpdates();
      toast.success('Updates linked!', { id: 'link' });
      refetch();
    } catch (e) {
      toast.error('Linking failed', { id: 'link' });
    }
  };

  return (
    <div className="space-y-6">
      {/* Header actions */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-0 flex items-center gap-2">
          <input
            type="text"
            value={newSubreddit}
            onChange={(e) => setNewSubreddit(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddSubreddit()}
            placeholder="Add subreddit (e.g., AskReddit)"
            className="input max-w-xs"
          />
          <button
            onClick={handleAddSubreddit}
            disabled={isAdding}
            className="btn-primary flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            Add
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleFetchAll}
            className="btn-secondary flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Fetch All
          </button>
          <button
            onClick={handleLinkUpdates}
            className="btn-secondary flex items-center gap-2"
          >
            <Link2 className="w-4 h-4" />
            Link Updates
          </button>
        </div>
      </div>

      {/* Active subreddits */}
      {subreddits && subreddits.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {subreddits.map((sub: any) => (
            <span
              key={sub.id}
              className="px-3 py-1 bg-primary/10 text-primary text-sm rounded-full font-medium"
            >
              {sub.display_name}
            </span>
          ))}
        </div>
      )}

      {/* Stories list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      ) : stories && stories.length > 0 ? (
        <div className="space-y-2">
          {stories.map((story: Story) => (
            <StoryCard key={story.id} story={story} />
          ))}
        </div>
      ) : (
        <div className="card p-12 text-center">
          <BookOpen className="w-12 h-12 mx-auto mb-4 text-gray-300" />
          <h3 className="text-lg font-semibold text-gray-500">No stories yet</h3>
          <p className="text-sm text-gray-400 mt-1">
            Add a subreddit and click "Fetch All" to get started
          </p>
        </div>
      )}
    </div>
  );
}
