import { create } from "zustand";

export interface VideoJob {
  videoId: number;
  storyId: number;
  status: string;
  progress: number;
  currentStep: string;
  queuePosition: number | null;
  errorMessage: string | null;
  isPaused: boolean;
  openedAt: number;
}

interface VideoJobsState {
  jobs: Record<number, VideoJob>;
  activeModalVideoId: number | null;
  activeModalStoryId: number | null;

  setActiveModal: (videoId: number | null, storyId?: number | null) => void;
  registerJob: (videoId: number, storyId: number, status?: string) => void;
  updateJob: (videoId: number, updates: Partial<VideoJob>) => void;
  removeJob: (videoId: number) => void;
  getJobForStory: (storyId: number) => VideoJob | null;
  isStoryActive: (storyId: number) => boolean;
  getActiveJobForStory: (storyId: number) => VideoJob | null;
  openModalForStory: (storyId: number, jobsState?: Record<number, VideoJob>) => number | null;
  cleanupTerminalJobs: () => void;
  getModalVideoId: (storyId: number, storyGeneratedVideo?: { id: number; status: string } | null) => number | null;
}

const TERMINAL_STATUSES = ["done", "failed", "cancelled"];

export const useVideoJobsStore = create<VideoJobsState>((set, get) => ({
  jobs: {},
  activeModalVideoId: null,
  activeModalStoryId: null,

  setActiveModal: (videoId, storyId) => {
    set({ activeModalVideoId: videoId, activeModalStoryId: storyId ?? null });
  },

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
          queuePosition: null,
          errorMessage: null,
          isPaused: false,
          openedAt: Date.now(),
          ...state.jobs[videoId],
        },
      },
    })),

  updateJob: (videoId, updates) =>
    set((state) => {
      const job = state.jobs[videoId];
      if (!job) return state;
      return {
        jobs: {
          ...state.jobs,
          [videoId]: { ...job, ...updates },
        },
      };
    }),

  removeJob: (videoId) =>
    set((state) => {
      const next = { ...state.jobs };
      delete next[videoId];
      return {
        jobs: next,
        activeModalVideoId:
          state.activeModalVideoId === videoId ? null : state.activeModalVideoId,
        activeModalStoryId:
          state.activeModalVideoId === videoId ? null : state.activeModalStoryId,
      };
    }),

  getJobForStory: (storyId) => {
    const jobs = Object.values(get().jobs);
    return (
      jobs.find(
        (j) =>
          j.storyId === storyId && !TERMINAL_STATUSES.includes(j.status)
      ) || null
    );
  },

  isStoryActive: (storyId) => {
    return get().getJobForStory(storyId) !== null;
  },

  getActiveJobForStory: (storyId) => {
    return get().getJobForStory(storyId);
  },

  openModalForStory: (storyId, jobsState) => {
    const jobs = jobsState || get().jobs;
    const job = Object.values(jobs).find(
      (j) => j.storyId === storyId && !TERMINAL_STATUSES.includes(j.status)
    );
    if (job) {
      set({ activeModalVideoId: job.videoId, activeModalStoryId: storyId });
      return job.videoId;
    }
    return null;
  },

  cleanupTerminalJobs: () => {
    set((state) => {
      const next: Record<number, VideoJob> = {};
      for (const [id, job] of Object.entries(state.jobs)) {
        const vid = Number(id);
        if (!TERMINAL_STATUSES.includes(job.status)) {
          next[vid] = job;
        }
      }
      return { jobs: next };
    });
  },

  /**
   * Get the videoId to show in the modal for a given story.
   * Checks: active tracked job, story's generated_video, parent story's video (for updates).
   */
  getModalVideoId: (storyId, storyGeneratedVideo) => {
    const state = get();

    // 1. Check if we have an active tracked job for this story
    const trackedJob = state.getJobForStory(storyId);
    if (trackedJob) {
      return trackedJob.videoId;
    }

    // 2. Check if story has an active generated_video in DB
    if (storyGeneratedVideo && !TERMINAL_STATUSES.includes(storyGeneratedVideo.status)) {
      // Register it so we track it
      state.registerJob(storyGeneratedVideo.id, storyId, storyGeneratedVideo.status);
      return storyGeneratedVideo.id;
    }

    // 3. Check active modal for this story
    if (state.activeModalStoryId === storyId && state.activeModalVideoId) {
      return state.activeModalVideoId;
    }

    return null;
  },
}));
