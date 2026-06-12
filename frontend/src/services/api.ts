import axios from "axios";
import { useNotificationStore } from "@/store";

export const API_BASE =
  import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

export function getVideoThumbnailUrl(
  videoId: number,
  cacheKey?: string | number,
): string {
  const qs = cacheKey != null ? `?v=${encodeURIComponent(String(cacheKey))}` : "";
  return `${API_BASE}/videos/${videoId}/thumbnail${qs}`;
}

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.response.use(
  (response) => {
    const method = response.config.method?.toLowerCase();
    const isMutation =
      method === "post" || method === "put" || method === "delete";
    const isNotificationEndpoint =
      response.config.url?.includes("/notifications");
    if (isMutation && !isNotificationEndpoint) {
      refreshNotifications().catch(() => {});
    }
    return response;
  },
  (error) => Promise.reject(error),
);

async function refreshNotifications() {
  try {
    const { data } = await axios.get(`${API_BASE}/notifications?limit=20`, {
      headers: { "Content-Type": "application/json" },
    });
    useNotificationStore.getState().setNotifications(data);
  } catch (e) {
    console.debug("Notification refresh failed:", e);
  }
}

export class SSEConnection {
  private eventSource: EventSource | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private listeners: Map<string, Set<(data: any) => void>> = new Map();

  connect(endpoint: string) {
    if (this.eventSource) return;
    const url = `${API_BASE.replace("/api/v1", "")}${endpoint}`;
    this.eventSource = new EventSource(url);
    this.eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const eventType = event.type || "message";
        this.emit(eventType, data);
      } catch (e) {
        console.error("SSE parse error:", e);
      }
    };
    this.eventSource.onerror = () => {
      this.disconnect();
      this.reconnectTimer = setTimeout(() => this.connect(endpoint), 5000);
    };
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  on(event: string, callback: (data: any) => void) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(callback);
  }

  off(event: string, callback: (data: any) => void) {
    this.listeners.get(event)?.delete(callback);
  }

  private emit(event: string, data: any) {
    this.listeners.get(event)?.forEach((cb) => cb(data));
    this.listeners.get("message")?.forEach((cb) => cb(data));
  }
}

export const sse = new SSEConnection();

/** Robust Video Progress SSE connection with proper cleanup and dedup */
export class VideoProgressConnection {
  private eventSource: EventSource | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private listeners: Set<(data: any) => void> = new Set();
  private currentEndpoint = "";
  private currentVideoId: number | null = null;
  private isTerminal = false;
  private isConnecting = false;
  private connectionCount = 0;
  private _lastEmittedData: any = null;
  private _duplicateCount = 0;

  connect(videoId: number) {
    const endpoint = `${API_BASE.replace("/api/v1", "")}/api/v1/sse/videos/${videoId}/progress`;

    // Already connected to this video and not terminal - skip
    if (
      this.currentVideoId === videoId &&
      this.currentEndpoint === endpoint &&
      this.eventSource &&
      !this.isTerminal
    ) {
      return;
    }

    // Prevent concurrent connection attempts
    if (this.isConnecting) {
      return;
    }

    // Disconnect previous connection
    this._disconnectInternal();

    this.isConnecting = true;
    this.currentEndpoint = endpoint;
    this.currentVideoId = videoId;
    this.isTerminal = false;
    this.connectionCount++;
    this._lastEmittedData = null;
    this._duplicateCount = 0;
    const currentConnection = this.connectionCount;

    try {
      this.eventSource = new EventSource(endpoint);
      this.isConnecting = false;

      this.eventSource.addEventListener("progress", (event) => {
        // Ignore events from stale connections
        if (currentConnection !== this.connectionCount) return;

        try {
          const data = JSON.parse((event as MessageEvent).data);

          // FIX 9: Always emit terminal states immediately
          const isTerminal = ["done", "failed", "cancelled", "deleted"].includes(
            data.status,
          );

          // FIX 9: Enhanced duplicate detection - compare queue_position and current_step too
          const isDuplicate =
            this._lastEmittedData &&
            this._lastEmittedData.status === data.status &&
            this._lastEmittedData.progress_percent === data.progress_percent &&
            this._lastEmittedData.current_step === data.current_step &&
            this._lastEmittedData.queue_position === data.queue_position;

          // FIX 9: Reset duplicate counter when entering a new non-terminal status
          if (
            this._lastEmittedData &&
            this._lastEmittedData.status !== data.status &&
            !isTerminal
          ) {
            this._duplicateCount = 0;
          }

          if (isDuplicate && !isTerminal) {
            this._duplicateCount++;
            // Only skip if we've seen the exact same non-terminal event more than 5 times
            if (this._duplicateCount > 5) {
              return;
            }
          } else {
            this._lastEmittedData = data;
            this._duplicateCount = 0;
          }

          if (isTerminal) {
            this.isTerminal = true;
          }

          this.listeners.forEach((cb) => {
            try {
              cb(data);
            } catch (e) {
              /* ignore callback errors */
            }
          });
        } catch (e) {
          console.error("Video progress event error:", e);
        }
      });

      this.eventSource.onerror = () => {
        if (currentConnection !== this.connectionCount) return;

        const wasTerminal = this.isTerminal;
        this._disconnectInternal();

        // FIX 9: Do NOT reconnect after terminal state
        if (wasTerminal) {
          return;
        }

        // Auto-reconnect if not terminal and still tracking this video
        if (!wasTerminal && this.currentVideoId === videoId) {
          this.reconnectTimer = setTimeout(() => {
            if (this.currentVideoId === videoId && !this.isTerminal) {
              this.connect(videoId);
            }
          }, 3000);
        }
      };

      this.eventSource.onopen = () => {
        if (currentConnection !== this.connectionCount) return;
      };
    } catch (e) {
      this.isConnecting = false;
      console.error("Failed to create EventSource:", e);
    }
  }

  /** Disconnect but preserve listeners for reconnect */
  private _disconnectInternal() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    this.connectionCount++; // Increment to invalidate stale callbacks
  }

  /** Full disconnect with listener cleanup */
  disconnect() {
    this._disconnectInternal();
    this.listeners.clear();
    this.currentEndpoint = "";
    this.currentVideoId = null;
    this.isTerminal = false;
    this.isConnecting = false;
    this._lastEmittedData = null;
    this._duplicateCount = 0;
  }

  onProgress(callback: (data: any) => void) {
    this.listeners.add(callback);
  }

  offProgress(callback: (data: any) => void) {
    this.listeners.delete(callback);
    if (this.listeners.size === 0) {
      this.disconnect();
    }
  }
}

export const videoProgressSSE = new VideoProgressConnection();

export const subredditApi = {
  list: () => api.get("/subreddits"),
  add: (name: string, settings?: Record<string, any>, force?: boolean) =>
    api.post(
      "/subreddits",
      { name, fetch_settings: settings },
      { params: { force } },
    ),
  delete: (id: number) => api.delete(`/subreddits/${id}`),
  deleteAll: () => api.delete("/subreddits"),
  fetch: (id: number) => api.post(`/subreddits/${id}/fetch`),
  fetchAll: () => api.post("/fetch-all"),
  fetchPreview: () => api.get("/fetch-preview"),
  fetchWithParams: (data: {
    subreddit_id?: number | null;
    sort: string;
    time_filter: string;
    limit: number;
  }) => api.post("/fetch", data),
};

export const storyApi = {
  list: (params?: Record<string, any>) => api.get("/stories", { params }),
  get: (id: number) => api.get(`/stories/${id}`),
  delete: (id: number) => api.delete(`/stories/${id}`),
  deleteAll: () => api.delete("/stories"),
  getChain: (id: number) => api.get(`/stories/${id}/chain`),
  linkUpdates: (subreddit?: string) =>
    api.post("/stories/link-updates", {}, { params: { subreddit } }),
};

export const videoApi = {
  list: (status?: string) => api.get("/videos", { params: { status } }),
  get: (id: number) => api.get(`/videos/${id}`),
  generate: (data: Record<string, any>) => api.post("/videos/generate", data),
  validateBackground: (data: Record<string, any>) =>
    api.post("/videos/validate-background", data),
  uploadBackground: (formData: FormData) =>
    api.post("/videos/upload-background", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  getProgress: (id: number) => api.get(`/videos/${id}/progress`),
  pause: (id: number) => api.post(`/videos/${id}/pause`),
  resume: (id: number) => api.post(`/videos/${id}/resume`),
  cancel: (id: number) => api.post(`/videos/${id}/cancel`),
  retry: (id: number) => api.post(`/videos/${id}/retry`),
  delete: (id: number) => api.delete(`/videos/${id}`),
};

export const youtubeApi = {
  authStatus: () => api.get("/youtube/auth/status"),
  initiateAuth: () => api.post("/youtube/auth/initiate"),
  callback: (code: string, state: string) =>
    api.post("/youtube/auth/callback", { code, state }),
  logout: () => api.post("/youtube/auth/logout"),
  upload: (data: Record<string, any>) => api.post("/youtube/upload", data),
  getStats: (videoId: string) => api.get(`/youtube/videos/${videoId}/stats`),
  updateMetadata: (videoId: string, data: Record<string, any>) =>
    api.put(`/youtube/videos/${videoId}`, data),
  updatePrivacy: (videoId: string, privacy: string) =>
    api.put(`/youtube/videos/${videoId}/privacy`, { privacy_status: privacy }),
  delete: (videoId: string) => api.delete(`/youtube/videos/${videoId}`),
};

export const notificationApi = {
  list: (unreadOnly?: boolean, limit?: number) =>
    api.get("/notifications", { params: { unread_only: unreadOnly, limit } }),
  markRead: (id: number) => api.post(`/notifications/${id}/read`),
  markAllRead: () => api.post("/notifications/read-all"),
  delete: (id: number) => api.delete(`/notifications/${id}`),
  deleteAll: () => api.delete("/notifications"),
};

export const settingsApi = {
  get: (key: string, decrypt?: boolean) =>
    api.get(`/settings/${key}`, { params: { decrypt } }),
  set: (key: string, value: string, encrypt?: boolean) =>
    api.post("/settings", { key, value, encrypt }),
  batchGet: (keys: string[]) =>
    api.get("/settings/batch/keys", { params: { keys: keys.join(",") } }),
};

export const ffmpegSettingsApi = {
  getAll: () => api.get("/settings/ffmpeg/video"),
  set: (key: string, value: string) =>
    api.post("/settings/ffmpeg/video", { key, value }),
};

export const automationApi = {
  listTemplates: () => api.get("/automation/templates"),
  getTemplate: (id: number) => api.get(`/automation/templates/${id}`),
  createTemplate: (data: Record<string, any>) =>
    api.post("/automation/templates", data),
  updateTemplate: (id: number, data: Record<string, any>) =>
    api.put(`/automation/templates/${id}`, data),
  deleteTemplate: (id: number) => api.delete(`/automation/templates/${id}`),
  toggleTemplate: (id: number) =>
    api.post(`/automation/templates/${id}/toggle`),
  runTemplate: (id: number) => api.post(`/automation/templates/${id}/run`),
  getRuns: (id: number) => api.get(`/automation/templates/${id}/runs`),
};

export const ffmpegApi = {
  getStatus: () => api.get("/ffmpeg/status"),
  install: () => api.post("/ffmpeg/install"),
  retry: () => api.post("/ffmpeg/retry"),
  setPath: (ffmpegPath: string, ffprobePath?: string) =>
    api.post("/ffmpeg/set-path", {
      ffmpeg_path: ffmpegPath,
      ffprobe_path: ffprobePath,
    }),
  checkPath: (path: string) =>
    api.get("/ffmpeg/check-path", { params: { path } }),
  reset: () => api.delete("/ffmpeg/reset"),
  cancel: () => api.post("/ffmpeg/cancel"),
};

export const ttsLocalApi = {
  getStatus: () => api.get("/tts_local/status"),
  listVoices: () => api.get("/tts_local/voices"),
};
