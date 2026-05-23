import { useState, useEffect, useCallback } from "react";
import { VideoProgressEvent } from "@/types";
import { videoProgressSSE } from "@/services/api";

interface UseVideoProgressOptions {
  videoId: number | null;
  onComplete?: (data: VideoProgressEvent) => void;
}

export function useVideoProgress({
  videoId,
  onComplete,
}: UseVideoProgressOptions) {
  const [progress, setProgress] = useState<VideoProgressEvent | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  const handleProgress = useCallback(
    (data: VideoProgressEvent) => {
      setProgress(data);
      setIsConnected(true);

      if (["done", "failed", "cancelled"].includes(data.status)) {
        setTimeout(() => {
          setIsConnected(false);
          onComplete?.(data);
        }, 1000);
      }
    },
    [onComplete],
  );

  useEffect(() => {
    if (!videoId) {
      setProgress(null);
      setIsConnected(false);
      return;
    }

    videoProgressSSE.connect(videoId);
    videoProgressSSE.onProgress(handleProgress);
    setIsConnected(true);

    return () => {
      videoProgressSSE.offProgress(handleProgress);
    };
  }, [videoId, handleProgress]);

  return { progress, isConnected };
}
