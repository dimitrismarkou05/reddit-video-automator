import { useEffect, useRef, useState, useCallback } from "react";
import { videoApi, videoProgressSSE } from "@/services/api";
import { mergeVideoProgress } from "@/utils/videoQueries";

export interface VideoProgressData {
  video_id: number;
  status: string;
  progress_percent: number;
  current_step: string;
  status_message?: string;
  step_progress: number;
  error_message: string | null;
  error_type: string | null;
  error_step: string | null;
  queue_position: number | null;
  is_paused: boolean;
  retry_count: number;
  thumbnail_path?: string;
  video_path?: string;
}

interface UseVideoProgressOptions {
  videoId: number | null;
  onComplete?: (data: VideoProgressData) => void;
  onError?: (data: VideoProgressData) => void;
  onQueue?: (data: VideoProgressData) => void;
}

// Terminal statuses that should trigger reconnection on change
const TERMINAL_STATUSES = ["done", "failed", "cancelled", "deleted"];

export function useVideoProgress({
  videoId,
  onComplete,
  onError,
  onQueue,
}: UseVideoProgressOptions) {
  const [progress, setProgress] = useState<VideoProgressData | null>(null);
  const lastVideoIdRef = useRef<number | null>(null);
  const isConnectedRef = useRef(false);
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);
  const onQueueRef = useRef(onQueue);
  const terminalNotifiedRef = useRef(false);
  // FIX 11: Track previous status to detect terminal -> non-terminal transitions
  const prevStatusRef = useRef<string | null>(null);
  const forceReconnectRef = useRef(false);

  // Keep callback refs up to date
  useEffect(() => {
    onCompleteRef.current = onComplete;
    onErrorRef.current = onError;
    onQueueRef.current = onQueue;
  }, [onComplete, onError, onQueue]);

  const handleProgress = useCallback((data: VideoProgressData) => {
    setProgress((prev) => {
      const merged = mergeVideoProgress(prev, data);
      if (!merged) {
        return prev;
      }

      // FIX 11: Detect transition from terminal to non-terminal (retry case)
      const wasTerminal = prev && TERMINAL_STATUSES.includes(prev.status);
      const isNowNonTerminal = !TERMINAL_STATUSES.includes(merged.status);
      if (wasTerminal && isNowNonTerminal) {
        forceReconnectRef.current = true;
        terminalNotifiedRef.current = false;
      }

      const isTerminal = TERMINAL_STATUSES.includes(merged.status);

      // Notify queue status
      if (
        merged.status === "queued" &&
        merged.queue_position &&
        onQueueRef.current
      ) {
        onQueueRef.current(merged);
      }

      // Handle terminal states - only notify once per videoId
      if (isTerminal) {
        if (!terminalNotifiedRef.current) {
          terminalNotifiedRef.current = true;
          if (merged.status === "done") {
            onCompleteRef.current?.(merged);
          } else {
            onErrorRef.current?.(merged);
          }
        }
      } else {
        terminalNotifiedRef.current = false;
      }

      prevStatusRef.current = merged.status;
      return merged;
    });
  }, []);

  useEffect(() => {
    // FIX 11: Force reconnect on retry (terminal -> non-terminal transition detected)
    if (forceReconnectRef.current && videoId && lastVideoIdRef.current === videoId) {
      forceReconnectRef.current = false;
      videoProgressSSE.disconnect();
      isConnectedRef.current = false;
    }

    // No videoId - unregister listener and reset
    if (!videoId) {
      if (lastVideoIdRef.current !== null) {
        videoProgressSSE.offProgress(handleProgress);
      }
      setProgress(null);
      lastVideoIdRef.current = null;
      isConnectedRef.current = false;
      terminalNotifiedRef.current = false;
      prevStatusRef.current = null;
      return;
    }

    // Reset terminal notification when subscribing to a video
    if (lastVideoIdRef.current !== videoId) {
      terminalNotifiedRef.current = false;
      prevStatusRef.current = null;
    }

    lastVideoIdRef.current = videoId;
    isConnectedRef.current = true;

    videoApi
      .getProgress(videoId)
      .then(({ data }) => {
        if (data) {
          handleProgress(data as VideoProgressData);
        }
      })
      .catch((err: { response?: { status?: number } }) => {
        if (err.response?.status === 404) {
          handleProgress({
            video_id: videoId,
            status: "failed",
            progress_percent: 0,
            current_step: "not_found",
            status_message: "Video not found",
            step_progress: 0,
            error_message: "Video record not found",
            error_type: "NotFound",
            error_step: "lookup",
            queue_position: null,
            is_paused: false,
            retry_count: 0,
          });
        }
      });

    videoProgressSSE.onProgress(handleProgress);
    videoProgressSSE.connect(videoId);

    return () => {
      videoProgressSSE.offProgress(handleProgress);
      if (lastVideoIdRef.current === videoId) {
        isConnectedRef.current = false;
        lastVideoIdRef.current = null;
      }
    };
  }, [videoId, handleProgress]);

  return { progress };
}
