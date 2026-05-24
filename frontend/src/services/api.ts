import axios from "axios";
import { useNotificationStore } from "@/store";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

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

export class VideoProgressConnection {
  private eventSource: EventSource | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private listeners: Set<(data: any) => void> = new Set();
  private currentEndpoint: string = "";
  private currentVideoId: number | null = null;
  private isTerminal = false;

  connect(videoId: number) {
    const endpoint = `${API_BASE.replace("/api/v1", "")}/api/v1/sse/videos/${videoId}/progress`;
    if (this.eventSource && this.currentEndpoint === endpoint) return;

    this.disconnect();
    this.currentEndpoint = endpoint;
    this.currentVideoId = videoId;
    this.isTerminal = false;

    this.eventSource = new EventSource(endpoint);

    this.eventSource.addEventListener("progress", (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data);
        if (["done", "failed", "cancelled"].includes(data.status)) {
          this.isTerminal = true;
        }
        this.listeners.forEach((cb) => cb(data));
      } catch (e) {
        console.error("Video progress event error:", e);
      }
    });

    this.eventSource.addEventListener("error", (event) => {
      // Backend-sent "event: error" (e.g. "Video not found")
      if (event instanceof MessageEvent) {
        try {
          const data = JSON.parse(event.data);
          this.isTerminal = true;
          this.listeners.forEach((cb) => cb(data));
        } catch (e) {
          console.error("Video SSE error event parse error:", e);
        }
      }
    });

    this.eventSource.onerror = () => {
      this.disconnect();
      // Only reconnect if the video hasn't reached a terminal / not-found state
      if (!this.isTerminal && this.currentVideoId !== null) {
        this.reconnectTimer = setTimeout(() => {
          this.connect(this.currentVideoId!);
        }, 3000);
      }
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

  onProgress(callback: (data: any) => void) {
    this.listeners.add(callback);
  }

  offProgress(callback: (data: any) => void) {
    this.listeners.delete(callback);
    // Auto-disconnect when nothing is listening so we don't leak connections
    if (this.listeners.size === 0) {
      this.disconnect();
      this.currentEndpoint = "";
      this.currentVideoId = null;
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
  getProgress: (id: number) => api.get(`/videos/${id}/progress`),
  pause: (id: number) => api.post(`/videos/${id}/pause`),
  resume: (id: number) => api.post(`/videos/${id}/resume`),
  cancel: (id: number) => api.post(`/videos/${id}/cancel`),
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
