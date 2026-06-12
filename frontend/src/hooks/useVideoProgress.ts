import { useEffect, useRef, useCallback, useSyncExternalStore } from "react";
import { videoApi, videoProgressSSE } from "@/services/api";
import {
  getMergedVideoProgress,
  subscribeVideoProgressSession,
} from "@/store/videoProgressSession";
import {
  ingestVideoProgress,
  type VideoProgressData,
} from "@/utils/videoQueries";

export type { VideoProgressData };

interface UseVideoProgressOptions {
  videoId: number | null;
  onComplete?: (data: VideoProgressData) => void;
  onError?: (data: VideoProgressData) => void;
  onQueue?: (data: VideoProgressData) => void;
}

const TERMINAL_STATUSES = ["done", "failed", "cancelled", "deleted"];

/** Ref-count SSE subscriptions per video so multiple components share one connection. */
const subscriberCountByVideo = new Map<number, number>();

export function useVideoProgress({
  videoId,
  onComplete,
  onError,
  onQueue,
}: UseVideoProgressOptions) {
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);
  const onQueueRef = useRef(onQueue);
  const terminalNotifiedRef = useRef(false);
  const prevStatusRef = useRef<string | null>(null);
  const forceReconnectRef = useRef(false);
  const lastVideoIdRef = useRef<number | null>(null);

  const progress = useSyncExternalStore(
    subscribeVideoProgressSession,
    () => (videoId != null ? getMergedVideoProgress(videoId) : null),
    () => null,
  );

  useEffect(() => {
    onCompleteRef.current = onComplete;
    onErrorRef.current = onError;
    onQueueRef.current = onQueue;
  }, [onComplete, onError, onQueue]);

  const handleProgress = useCallback((data: VideoProgressData) => {
    const prev = getMergedVideoProgress(data.video_id);
    const merged = ingestVideoProgress(data);
    if (!merged) return;

    const wasTerminal = prev && TERMINAL_STATUSES.includes(prev.status);
    const isNowNonTerminal = !TERMINAL_STATUSES.includes(merged.status);
    if (wasTerminal && isNowNonTerminal) {
      forceReconnectRef.current = true;
      terminalNotifiedRef.current = false;
    }

    const isTerminal = TERMINAL_STATUSES.includes(merged.status);

    if (
      merged.status === "queued" &&
      merged.queue_position &&
      onQueueRef.current
    ) {
      onQueueRef.current(merged);
    }

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
  }, []);

  useEffect(() => {
    if (
      forceReconnectRef.current &&
      videoId &&
      lastVideoIdRef.current === videoId
    ) {
      forceReconnectRef.current = false;
      videoProgressSSE.disconnect();
    }

    if (!videoId) {
      if (lastVideoIdRef.current !== null) {
        videoProgressSSE.offProgress(handleProgress);
        const prevId = lastVideoIdRef.current;
        const count = (subscriberCountByVideo.get(prevId) ?? 1) - 1;
        if (count <= 0) {
          subscriberCountByVideo.delete(prevId);
        } else {
          subscriberCountByVideo.set(prevId, count);
        }
      }
      lastVideoIdRef.current = null;
      terminalNotifiedRef.current = false;
      prevStatusRef.current = null;
      return;
    }

    if (lastVideoIdRef.current !== videoId) {
      terminalNotifiedRef.current = false;
      prevStatusRef.current = null;
    }

    const isFirstSubscriber =
      (subscriberCountByVideo.get(videoId) ?? 0) === 0;
    subscriberCountByVideo.set(
      videoId,
      (subscriberCountByVideo.get(videoId) ?? 0) + 1,
    );

    lastVideoIdRef.current = videoId;

    videoProgressSSE.onProgress(handleProgress);

    if (isFirstSubscriber) {
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

      videoProgressSSE.connect(videoId);
    }

    return () => {
      videoProgressSSE.offProgress(handleProgress);
      const count = (subscriberCountByVideo.get(videoId) ?? 1) - 1;
      if (count <= 0) {
        subscriberCountByVideo.delete(videoId);
        if (lastVideoIdRef.current === videoId) {
          lastVideoIdRef.current = null;
        }
      } else {
        subscriberCountByVideo.set(videoId, count);
      }
    };
  }, [videoId, handleProgress]);

  return { progress };
}
