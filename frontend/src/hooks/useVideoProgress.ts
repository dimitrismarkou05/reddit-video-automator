import { useEffect, useRef, useState, useCallback } from "react";
import { videoProgressSSE } from "@/services/api";

export interface VideoProgressData {
  video_id: number;
  status: string;
  progress_percent: number;
  current_step: string;
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

export function useVideoProgress({ videoId, onComplete, onError, onQueue }: UseVideoProgressOptions) {
  const [progress, setProgress] = useState<VideoProgressData | null>(null);
  const lastVideoIdRef = useRef<number | null>(null);
  const isConnectedRef = useRef(false);
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);
  const onQueueRef = useRef(onQueue);
  const terminalNotifiedRef = useRef(false);

  // Keep callback refs up to date
  useEffect(() => {
    onCompleteRef.current = onComplete;
    onErrorRef.current = onError;
    onQueueRef.current = onQueue;
  }, [onComplete, onError, onQueue]);

  const handleProgress = useCallback((data: VideoProgressData) => {
    setProgress(data);

    // Notify queue status
    if (data.status === "queued" && data.queue_position && onQueueRef.current) {
      onQueueRef.current(data);
    }

    // Handle terminal states - only notify once
    if (["done", "failed", "cancelled"].includes(data.status)) {
      if (!terminalNotifiedRef.current) {
        terminalNotifiedRef.current = true;
        if (data.status === "done") {
          onCompleteRef.current?.(data);
        } else {
          onErrorRef.current?.(data);
        }
      }
    }
  }, []);

  useEffect(() => {
    // No videoId - disconnect and reset
    if (!videoId) {
      if (isConnectedRef.current) {
        videoProgressSSE.disconnect();
        isConnectedRef.current = false;
      }
      setProgress(null);
      lastVideoIdRef.current = null;
      terminalNotifiedRef.current = false;
      return;
    }

    // Same videoId already connected - skip
    if (lastVideoIdRef.current === videoId && isConnectedRef.current) {
      return;
    }

    // Disconnect from previous video if any
    if (isConnectedRef.current) {
      videoProgressSSE.disconnect();
      isConnectedRef.current = false;
    }

    // Reset terminal notification for new video
    terminalNotifiedRef.current = false;

    // Connect to new video
    lastVideoIdRef.current = videoId;
    isConnectedRef.current = true;

    videoProgressSSE.onProgress(handleProgress);
    videoProgressSSE.connect(videoId);

    return () => {
      // Only disconnect if we're still connected to this video
      if (lastVideoIdRef.current === videoId) {
        videoProgressSSE.offProgress(handleProgress);
        isConnectedRef.current = false;
        lastVideoIdRef.current = null;
      }
    };
  }, [videoId, handleProgress]);

  return { progress };
}
