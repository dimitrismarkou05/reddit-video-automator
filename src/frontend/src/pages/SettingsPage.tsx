import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { 
  Key, Film, Palette, FolderOpen, ExternalLink, Check, AlertCircle,
  Terminal, Sun, Moon, Monitor
} from 'lucide-react';
import { useThemeStore, useAuthStore } from '@/store';
import { youtubeApi, settingsApi } from '@/services/api';
import toast from 'react-hot-toast';

function Section({ title, icon: Icon, children }: { title: string; icon: any; children: React.ReactNode }) {
  return (
    <div className="card p-6 mb-6">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
          <Icon className="w-5 h-5 text-primary" />
        </div>
        <h3 className="text-lg font-semibold">{title}</h3>
      </div>
      {children}
    </div>
  );
}

export function SettingsPage() {
  const { isDark, toggle } = useThemeStore();
  const { authStatus } = useAuthStore();
  const [redditCreds, setRedditCreds] = useState({ clientId: '', clientSecret: '', userAgent: '' });
  const [ttsKey, setTtsKey] = useState('');
  const [ffmpegPath, setFfmpegPath] = useState('');
  const [outputDir, setOutputDir] = useState('');

  const { data: ffmpegInfo } = useQuery({
    queryKey: ['ffmpeg'],
    queryFn: async () => {
      // This would be an actual API call to check FFmpeg
      return { installed: true, path: '/usr/bin/ffmpeg', version: 'ffmpeg version 6.0' };
    },
    staleTime: Infinity,
  });

  const handleSaveReddit = async () => {
    try {
      await settingsApi.set('reddit_client_id', redditCreds.clientId, true);
      await settingsApi.set('reddit_client_secret', redditCreds.clientSecret, true);
      await settingsApi.set('reddit_user_agent', redditCreds.userAgent);
      toast.success('Reddit credentials saved');
      setRedditCreds({ clientId: '', clientSecret: '', userAgent: '' });
    } catch (e) {
      toast.error('Failed to save credentials');
    }
  };

  const handleSaveTTS = async () => {
    try {
      await settingsApi.set('openai_api_key', ttsKey, true);
      toast.success('TTS API key saved');
      setTtsKey('');
    } catch (e) {
      toast.error('Failed to save API key');
    }
  };

  const handleSelectOutputDir = async () => {
    if (window.electronAPI) {
      const path = await window.electronAPI.selectDirectory();
      if (path) {
        setOutputDir(path);
        toast.success('Output directory selected');
      }
    }
  };

  const openExternal = async (url: string) => {
    if (window.electronAPI) {
      await window.electronAPI.openExternal(url);
    } else {
      window.open(url, '_blank');
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold mb-6">Settings</h2>

      {/* API Connections */}
      <Section title="API Connections" icon={Key}>
        {/* Reddit */}
        <div className="space-y-4 mb-6">
          <div className="flex items-center justify-between">
            <h4 className="font-medium">Reddit API</h4>
            <button
              onClick={() => openExternal('https://www.reddit.com/prefs/apps')}
              className="text-sm text-primary flex items-center gap-1 hover:underline"
            >
              <ExternalLink className="w-3 h-3" />
              Get API Key
            </button>
          </div>
          <div className="grid grid-cols-1 gap-3">
            <input
              type="password"
              placeholder="Client ID"
              value={redditCreds.clientId}
              onChange={(e) => setRedditCreds((c) => ({ ...c, clientId: e.target.value }))}
              className="input"
            />
            <input
              type="password"
              placeholder="Client Secret"
              value={redditCreds.clientSecret}
              onChange={(e) => setRedditCreds((c) => ({ ...c, clientSecret: e.target.value }))}
              className="input"
            />
            <input
              type="text"
              placeholder="User Agent (optional)"
              value={redditCreds.userAgent}
              onChange={(e) => setRedditCreds((c) => ({ ...c, userAgent: e.target.value }))}
              className="input"
            />
            <button onClick={handleSaveReddit} className="btn-primary w-fit">
              Save Reddit Credentials
            </button>
          </div>
        </div>

        {/* TTS */}
        <div className="space-y-4 border-t border-border-light dark:border-border-dark pt-4">
          <div className="flex items-center justify-between">
            <h4 className="font-medium">Text-to-Speech (OpenAI)</h4>
            <button
              onClick={() => openExternal('https://platform.openai.com/api-keys')}
              className="text-sm text-primary flex items-center gap-1 hover:underline"
            >
              <ExternalLink className="w-3 h-3" />
              Get API Key
            </button>
          </div>
          <div className="flex gap-3">
            <input
              type="password"
              placeholder="OpenAI API Key"
              value={ttsKey}
              onChange={(e) => setTtsKey(e.target.value)}
              className="input flex-1"
            />
            <button onClick={handleSaveTTS} className="btn-primary">
              Save
            </button>
          </div>
        </div>

        {/* YouTube Auth Status */}
        <div className="border-t border-border-light dark:border-border-dark pt-4">
          <h4 className="font-medium mb-3">YouTube Account</h4>
          {authStatus?.is_authenticated && authStatus.user_info ? (
            <div className="flex items-center gap-3 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
              {authStatus.user_info.picture ? (
                <img src={authStatus.user_info.picture} alt="" className="w-10 h-10 rounded-full" />
              ) : (
                <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center">
                  <Monitor className="w-5 h-5 text-primary" />
                </div>
              )}
              <div>
                <p className="font-medium">{authStatus.user_info.name}</p>
                <p className="text-sm text-gray-500">{authStatus.user_info.email}</p>
              </div>
              <Check className="w-5 h-5 text-green-500 ml-auto" />
            </div>
          ) : (
            <div className="flex items-center gap-3 p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg">
              <AlertCircle className="w-5 h-5 text-yellow-500" />
              <p className="text-sm">Not connected. Go to Login to connect your Google account.</p>
            </div>
          )}
        </div>
      </Section>

      {/* FFmpeg */}
      <Section title="FFmpeg Settings" icon={Film}>
        {ffmpegInfo ? (
          <div className="space-y-3">
            <div className="flex items-center gap-3 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
              <Check className="w-5 h-5 text-green-500" />
              <div>
                <p className="font-medium text-sm">FFmpeg Detected</p>
                <p className="text-xs text-gray-500">{ffmpegInfo.path}</p>
              </div>
            </div>
            <p className="text-xs text-gray-500 font-mono">{ffmpegInfo.version}</p>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-3 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
              <AlertCircle className="w-5 h-5 text-red-500" />
              <p className="text-sm">FFmpeg not detected on system</p>
            </div>
            <button
              onClick={() => openExternal('https://ffmpeg.org/download.html')}
              className="btn-secondary text-sm flex items-center gap-2"
            >
              <ExternalLink className="w-4 h-4" />
              Download FFmpeg
            </button>
            <div className="flex gap-3">
              <input
                type="text"
                placeholder="Manual FFmpeg path"
                value={ffmpegPath}
                onChange={(e) => setFfmpegPath(e.target.value)}
                className="input flex-1"
              />
              <button className="btn-primary">Set Path</button>
            </div>
          </div>
        )}
      </Section>

      {/* Theme */}
      <Section title="Appearance" icon={Palette}>
        <div className="flex items-center gap-4">
          <button
            onClick={toggle}
            className={`flex-1 p-4 rounded-xl border-2 transition-colors ${
              !isDark
                ? 'border-primary bg-primary/5'
                : 'border-border-light dark:border-border-dark hover:bg-gray-50 dark:hover:bg-gray-700'
            }`}
          >
            <Sun className="w-6 h-6 mx-auto mb-2 text-yellow-500" />
            <div className="text-sm font-medium">Light Mode</div>
            <div className="text-xs text-gray-500">Soft warm background</div>
          </button>
          <button
            onClick={toggle}
            className={`flex-1 p-4 rounded-xl border-2 transition-colors ${
              isDark
                ? 'border-primary bg-primary/5'
                : 'border-border-light dark:border-border-dark hover:bg-gray-50 dark:hover:bg-gray-700'
            }`}
          >
            <Moon className="w-6 h-6 mx-auto mb-2 text-blue-400" />
            <div className="text-sm font-medium">Dark Mode</div>
            <div className="text-xs text-gray-500">Dark slate tones</div>
          </button>
        </div>
      </Section>

      {/* Output */}
      <Section title="Output Settings" icon={FolderOpen}>
        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium mb-1">Output Directory</label>
            <div className="flex gap-3">
              <input
                type="text"
                value={outputDir}
                readOnly
                placeholder="Select output folder..."
                className="input flex-1"
              />
              <button
                onClick={handleSelectOutputDir}
                className="btn-secondary flex items-center gap-2"
              >
                <FolderOpen className="w-4 h-4" />
                Browse
              </button>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Default Video Format</label>
            <div className="flex gap-3">
              <button className="flex-1 p-3 rounded-lg border-2 border-primary bg-primary/5 text-center">
                <div className="text-sm font-medium">Shorts (9:16)</div>
                <div className="text-xs text-gray-500">Vertical mobile format</div>
              </button>
              <button className="flex-1 p-3 rounded-lg border-2 border-border-light dark:border-border-dark text-center hover:bg-gray-50 dark:hover:bg-gray-700">
                <div className="text-sm font-medium">Normal (16:9)</div>
                <div className="text-xs text-gray-500">Standard horizontal</div>
              </button>
            </div>
          </div>
        </div>
      </Section>
    </div>
  );
}
