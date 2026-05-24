import { create } from "zustand";
import type { TtsStatus } from "@/types";

interface TtsState {
  status: TtsStatus | null;
  isChecking: boolean;
  isInstalling: boolean;
  installProgress: number;
  installStep: string;
  currentMirror: string | undefined;
  retryCount: number;
  installError: string | null;
  setStatus: (status: TtsStatus) => void;
  startInstall: () => void;
  updateProgress: (
    progress: number,
    step: string,
    mirror?: string,
    retry?: number,
  ) => void;
  finishInstall: (status: TtsStatus) => void;
  failInstall: (error: string) => void;
  resetInstall: () => void;
  setChecking: (checking: boolean) => void;
}

export const useTtsStore = create<TtsState>((set) => ({
  status: null,
  isChecking: false,
  isInstalling: false,
  installProgress: 0,
  installStep: "",
  currentMirror: undefined,
  retryCount: 0,
  installError: null,

  setStatus: (status) => set({ status }),

  startInstall: () =>
    set({
      isInstalling: true,
      installProgress: 0,
      installStep: "Starting installation...",
      currentMirror: undefined,
      retryCount: 0,
      installError: null,
    }),

  updateProgress: (progress, step, mirror, retry) =>
    set({
      installProgress: progress,
      installStep: step,
      currentMirror: mirror,
      retryCount: retry ?? 0,
    }),

  finishInstall: (status) =>
    set({
      status,
      isInstalling: false,
      installProgress: 100,
      installStep: "Installation complete",
      installError: null,
    }),

  failInstall: (error) =>
    set({
      isInstalling: false,
      installProgress: 0,
      installStep: "Installation failed",
      installError: error,
    }),

  resetInstall: () =>
    set({
      isInstalling: false,
      installProgress: 0,
      installStep: "",
      currentMirror: undefined,
      retryCount: 0,
      installError: null,
    }),

  setChecking: (checking) => set({ isChecking: checking }),
}));
