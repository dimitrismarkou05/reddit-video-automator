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

const TERMINAL_STATUSES = ["done", "failed", "cancelled", "deleted"];

type Listener = () => void;
const listeners = new Set<Listener>();

const mergedByVideoId = new Map<number, VideoProgressData>();
const peakByVideoId = new Map<number, number>();

function notify() {
  listeners.forEach((l) => l());
}

function shouldResetPeak(
  prev: VideoProgressData | null,
  next: VideoProgressData,
): boolean {
  if (TERMINAL_STATUSES.includes(next.status)) return true;
  return (
    next.status === "queued" &&
    next.progress_percent === 0 &&
    (prev?.progress_percent ?? 0) > 0
  );
}

/** Store a merged progress payload and update the session peak. */
export function commitVideoProgress(
  merged: VideoProgressData,
): VideoProgressData {
  const videoId = merged.video_id;
  const prev = mergedByVideoId.get(videoId) ?? null;

  if (shouldResetPeak(prev, merged)) {
    peakByVideoId.delete(videoId);
    mergedByVideoId.set(videoId, merged);
    notify();
    return merged;
  }

  const peak = Math.max(peakByVideoId.get(videoId) ?? 0, merged.progress_percent);
  peakByVideoId.set(videoId, peak);
  const withPeak = { ...merged, progress_percent: peak };
  mergedByVideoId.set(videoId, withPeak);
  notify();
  return withPeak;
}

export function getMergedVideoProgress(
  videoId: number,
): VideoProgressData | null {
  return mergedByVideoId.get(videoId) ?? null;
}

export function getPeakProgressPercent(videoId: number): number {
  return peakByVideoId.get(videoId) ?? 0;
}

export function applyPeakProgressPercent(
  videoId: number,
  percent: number,
): number {
  const peak = Math.max(peakByVideoId.get(videoId) ?? 0, percent);
  peakByVideoId.set(videoId, peak);
  return peak;
}

export function seedPeakProgressPercent(
  videoId: number,
  percent: number,
): void {
  if (percent <= 0) return;
  const peak = Math.max(peakByVideoId.get(videoId) ?? 0, percent);
  peakByVideoId.set(videoId, peak);
}

export function clearVideoProgressSession(videoId: number): void {
  mergedByVideoId.delete(videoId);
  peakByVideoId.delete(videoId);
  notify();
}

export function subscribeVideoProgressSession(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
