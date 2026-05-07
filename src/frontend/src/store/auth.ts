import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { YouTubeAuthStatus } from '@/types';

interface AuthState {
  authStatus: YouTubeAuthStatus | null;
  isLoading: boolean;
  setAuthStatus: (status: YouTubeAuthStatus | null) => void;
  setLoading: (loading: boolean) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      authStatus: null,
      isLoading: true,
      setAuthStatus: (status) => set({ authStatus: status, isLoading: false }),
      setLoading: (loading) => set({ isLoading: loading }),
      logout: () => set({ authStatus: null }),
    }),
    {
      name: 'rva-auth',
    }
  )
);
