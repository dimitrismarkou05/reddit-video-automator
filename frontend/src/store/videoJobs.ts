import { create } from "zustand";

interface VideoJob {
  videoId: number;
  storyId: number;
  status: string;
  progress: number;
  currentStep: string;
}

interface VideoJobsState {
  jobs: Record<number, VideoJob>;
  activeModalVideoId: number | null;
  setActiveModalVideoId: (id: number | null) => void;
  registerJob: (videoId: number, storyId: number, status?: string) => void;
  updateJob: (videoId: number, updates: Partial<VideoJob>) => void;
  removeJob: (videoId: number) => void;
  getJobForStory: (storyId: number) => VideoJob | null;
  isStoryActive: (storyId: number) => boolean;
}

export const useVideoJobsStore = create<VideoJobsState>((set, get) => ({
  jobs: {},
  activeModalVideoId: null,

  setActiveModalVideoId: (id) => set({ activeModalVideoId: id }),

  registerJob: (videoId, storyId, status = "queued") =>
    set((state) => ({
      jobs: {
        ...state.jobs,
        [videoId]: {
          videoId,
          storyId,
          status,
          progress: 0,
          currentStep: "queued",
          ...state.jobs[videoId],
        },
      },
    })),

  updateJob: (videoId, updates) =>
    set((state) => ({
      jobs: {
        ...state.jobs,
        [videoId]: { ...state.jobs[videoId], ...updates },
      },
    })),

  removeJob: (videoId) =>
    set((state) => {
      const next = { ...state.jobs };
      delete next[videoId];
      return { jobs: next };
    }),

  getJobForStory: (storyId) => {
    const jobs = Object.values(get().jobs);
    return (
      jobs.find(
        (j) =>
          j.storyId === storyId &&
          !["done", "failed", "cancelled"].includes(j.status)
      ) || null
    );
  },

  isStoryActive: (storyId) => {
    return get().getJobForStory(storyId) !== null;
  },
}));
