import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Video, ArrowRight, AlertCircle } from 'lucide-react';
import { useAuthStore } from '@/store';
import { youtubeApi } from '@/services/api';
import toast from 'react-hot-toast';

export function LoginPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const { setAuthStatus } = useAuthStore();

  const handleLogin = async () => {
    setIsLoading(true);
    setError('');

    try {
      // Check if YouTube is configured
      const { data: status } = await youtubeApi.authStatus();

      if (!status.is_configured) {
        setError('YouTube OAuth credentials not configured. Please set them in Settings first.');
        setIsLoading(false);
        return;
      }

      // Initiate OAuth flow
      const { data: flow } = await youtubeApi.initiateAuth();

      // Open auth URL in system browser
      if (window.electronAPI) {
        await window.electronAPI.openExternal(flow.auth_url);
      } else {
        window.open(flow.auth_url, '_blank');
      }

      // Show instructions
      toast.success('Google login opened in browser. Complete authorization and return.', {
        duration: 10000,
      });

      // Poll for auth status
      const checkInterval = setInterval(async () => {
        try {
          const { data: newStatus } = await youtubeApi.authStatus();
          if (newStatus.is_authenticated) {
            clearInterval(checkInterval);
            setAuthStatus(newStatus);
            toast.success(`Welcome, ${newStatus.user_info?.name || 'User'}!`);
            navigate('/stories');
          }
        } catch (e) {
          console.error('Auth check error:', e);
        }
      }, 3000);

      // Stop polling after 5 minutes
      setTimeout(() => {
        clearInterval(checkInterval);
        setIsLoading(false);
      }, 300000);

    } catch (e: any) {
      setError(e.response?.data?.detail || 'Failed to initiate login. Please try again.');
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background-light dark:bg-background-dark">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-primary flex items-center justify-center mx-auto mb-4 shadow-lg">
            <Video className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold">Reddit Video Automator</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-2">
            Transform Reddit stories into YouTube videos
          </p>
        </div>

        {/* Login Card */}
        <div className="card p-8">
          <h2 className="text-xl font-semibold mb-2">Welcome</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
            Sign in with your Google account to connect YouTube
          </p>

          {error && (
            <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-start gap-2">
              <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            </div>
          )}

          <button
            onClick={handleLogin}
            disabled={isLoading}
            className="w-full flex items-center justify-center gap-3 px-4 py-3 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg font-medium hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
          >
            {isLoading ? (
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-primary" />
            ) : (
              <>
                <svg className="w-5 h-5" viewBox="0 0 24 24">
                  <path
                    fill="#4285F4"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  />
                </svg>
                Sign in with Google
              </>
            )}
          </button>

          <div className="mt-6 text-center">
            <button
              onClick={() => navigate('/settings')}
              className="text-sm text-primary hover:text-primary-dark"
            >
              Configure API settings first →
            </button>
          </div>
        </div>

        <p className="text-center text-xs text-gray-400 mt-6">
          Reddit Video Automator v0.4.0 • Phase 4
        </p>
      </div>
    </div>
  );
}
