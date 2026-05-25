import { useEffect, useRef, useState, useCallback } from "react";
import { videoProgressSSE } from "@/services/api";

interface VideoProgressData {
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
  thumbnail_path?: string;
  video_path?: string;
}

interface UseVideoProgressOptions {
  videoId: number | null;
  onComplete?: (data: VideoProgressData) => void;
}

export function useVideoProgress({ videoId, onComplete }: UseVideoProgressOptions) {
  const [progress, setProgress] = useState<VideoProgressData | null>(null);
  const lastVideoIdRef = useRef<number | null>(null);
  const isConnectedRef = useRef(false);
  const onCompleteRef = useRef(onComplete);

  // Keep callback ref up to date
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  const handleProgress = useCallback((data: VideoProgressData) => {
    setProgress(data);

    // Call onComplete for terminal states
    if (["done", "failed", "cancelled"].includes(data.status)) {
      onCompleteRef.current?.(data);
    }
  }, []);

  useEffect(() => {
    // Only connect if we have a valid videoId and it's different from last time
    if (!videoId) {
      if (isConnectedRef.current) {
        videoProgressSSE.disconnect();
        isConnectedRef.current = false;
      }
      setProgress(null);
      lastVideoIdRef.current = null;
      return;
    }

    // If already connected to this videoId, don't reconnect
    if (lastVideoIdRef.current === videoId && isConnectedRef.current) {
      return;
    }

    // Disconnect from previous video if any
    if (isConnectedRef.current) {
      videoProgressSSE.disconnect();
      isConnectedRef.current = false;
    }

    // Connect to new video
    lastVideoIdRef.current = videoId;
    isConnectedRef.current = true;

    videoProgressSSE.onProgress(handleProgress);
    videoProgressSSE.connect(videoId);

    return () => {
      // Only disconnect if we're still connected to this video
      if (lastVideoIdRef.current === videoId) {
        videoProgressSSE.offProgress(handleProgress);
      }
    };
  }, [videoId, handleProgress]);

  return { progress };
}
