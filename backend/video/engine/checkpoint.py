"""Checkpoint step resolution for pause/resume.

Checkpoints must only record *completed* pipeline stages. In-progress step names
(e.g. compositing, generating_thumbnail) must be rolled back on pause so resume
re-runs the interrupted stage instead of skipping to thumbnail/done.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

COMPLETED_CHECKPOINT_STEPS = frozenset({
    "preparing",
    "tts_done",
    "transcribe_done",
    "subtitles_done",
    "selecting_background",
    "compositing_done",
})

# Map in-progress UI/pipeline steps → last fully completed checkpoint.
IN_PROGRESS_TO_CHECKPOINT: dict[str, str] = {
    "queued": "queued",
    "processing": "queued",
    "preparing": "queued",
    "downloading_model": "preparing",
    "tts": "preparing",
    "tts_synthesizing": "preparing",
    "transcribing": "tts_done",
    "generating_subtitles": "transcribe_done",
    "selecting_background": "subtitles_done",
    "compositing": "selecting_background",
    "ffmpeg_processing": "selecting_background",
    "generating_thumbnail": "selecting_background",
    "compositing_done": "compositing_done",
    "paused": "queued",
    "failed": "queued",
}

# Full pipeline step order for monotonic progress UI (includes in-progress steps).
PROGRESS_STEP_ORDER = [
    "queued",
    "preparing",
    "downloading_model",
    "tts_synthesizing",
    "tts_done",
    "transcribing",
    "transcribe_done",
    "generating_subtitles",
    "subtitles_done",
    "selecting_background",
    "compositing",
    "ffmpeg_processing",
    "compositing_done",
    "generating_thumbnail",
    "done",
    "failed",
    "cancelled",
    "paused",
    "processing",
]


def progress_step_index(step: str) -> int:
    try:
        return PROGRESS_STEP_ORDER.index(step)
    except ValueError:
        return 0


def is_regressive_progress_update(
    current_step: str,
    new_step: str,
    new_pct: int,
    prev_pct: int,
) -> bool:
    """True when a progress emit would walk the UI backward without gaining %."""
    if new_step in ("done", "failed", "cancelled", "paused", "deleted"):
        return False
    current = current_step or "queued"
    if progress_step_index(new_step) < progress_step_index(current):
        if new_pct <= prev_pct:
            return True
    return False


def step_label(step: str) -> str:
    """Human-readable label for a pipeline step (used in pause messages)."""
    labels = {
        "preparing": "Preparing script",
        "downloading_model": "Loading voice model",
        "tts_synthesizing": "Generating voice",
        "tts_done": "Voice ready",
        "transcribing": "Transcribing audio",
        "transcribe_done": "Transcription complete",
        "generating_subtitles": "Building subtitles",
        "subtitles_done": "Subtitles ready",
        "selecting_background": "Selecting background",
        "compositing": "Rendering video",
        "ffmpeg_processing": "Rendering video",
        "compositing_done": "Video rendered",
        "generating_thumbnail": "Creating thumbnail",
        "queued": "Queued",
        "processing": "Processing",
        "paused": "Paused",
    }
    return labels.get(step, step.replace("_", " ").title())


def paused_status_message(video) -> str:
    """Status message for SSE when generation is paused."""
    step = getattr(video, "current_step", None) or "processing"
    return f"Paused — {step_label(step)}"


# Order for picking the most conservative (earliest) completed step.
_STEP_ORDER = [
    "queued",
    "preparing",
    "tts_done",
    "transcribe_done",
    "subtitles_done",
    "selecting_background",
    "compositing_done",
]


def _step_index(step: str) -> int:
    try:
        return _STEP_ORDER.index(step)
    except ValueError:
        return 0


def _earlier_step(a: str, b: str) -> str:
    return a if _step_index(a) <= _step_index(b) else b


def _video_file_valid(path: Optional[str], min_bytes: int = 1024) -> bool:
    if not path:
        return False
    try:
        p = Path(path)
        return p.is_file() and p.stat().st_size >= min_bytes
    except OSError:
        return False


def infer_checkpoint_step(video) -> str:
    """Infer the last completed checkpoint from artifacts and DB status."""
    checkpoint: dict[str, Any] = dict(video.temp_files_json or {})

    video_path = checkpoint.get("video_path") or getattr(video, "video_path", None)
    if _video_file_valid(video_path):
        return "compositing_done"

    if checkpoint.get("bg_video") or getattr(video, "selected_background_video", None):
        return "selecting_background"

    if checkpoint.get("subtitle_path") or getattr(video, "subtitle_ass_path", None):
        return "subtitles_done"

    if checkpoint.get("whisper_result") or getattr(video, "whisper_result_json", None):
        return "transcribe_done"

    if checkpoint.get("audio_path") or getattr(video, "tts_audio_path", None):
        return "tts_done"

    status = getattr(video, "status", None)
    status_map = {
        "tts_done": "tts_done",
        "transcribe_done": "transcribe_done",
        "subtitles_done": "subtitles_done",
        "compositing_done": "compositing_done",
    }
    if status in status_map:
        mapped = status_map[status]
        if mapped == "compositing_done" and not _video_file_valid(video_path):
            return "selecting_background"
        return mapped

    raw = checkpoint.get("step")
    if raw in COMPLETED_CHECKPOINT_STEPS:
        if raw == "compositing_done" and not _video_file_valid(video_path):
            return "selecting_background"
        return raw

    if raw in IN_PROGRESS_TO_CHECKPOINT:
        return IN_PROGRESS_TO_CHECKPOINT[raw]

    current = getattr(video, "current_step", None) or "queued"
    if current in IN_PROGRESS_TO_CHECKPOINT:
        return IN_PROGRESS_TO_CHECKPOINT[current]

    return "queued"


def resolve_checkpoint_step(video) -> str:
    """Resolve a safe checkpoint step for resume (never an in-progress step name)."""
    checkpoint: dict[str, Any] = dict(video.temp_files_json or {})
    step = infer_checkpoint_step(video)

    raw = checkpoint.get("step")
    if raw in COMPLETED_CHECKPOINT_STEPS:
        if raw == "compositing_done" and not _video_file_valid(
            checkpoint.get("video_path") or getattr(video, "video_path", None)
        ):
            step = _earlier_step(step, "selecting_background")
        else:
            step = _earlier_step(step, raw)
    elif raw in IN_PROGRESS_TO_CHECKPOINT:
        step = _earlier_step(step, IN_PROGRESS_TO_CHECKPOINT[raw])

    current = getattr(video, "current_step", None)
    if current in IN_PROGRESS_TO_CHECKPOINT:
        step = _earlier_step(step, IN_PROGRESS_TO_CHECKPOINT[current])

    if step == "compositing_done":
        video_path = checkpoint.get("video_path") or getattr(video, "video_path", None)
        if not _video_file_valid(video_path):
            step = "selecting_background"

    return step


def build_checkpoint_payload(video, step: Optional[str] = None) -> dict[str, Any]:
    """Build temp_files_json with artifact paths and a safe completed step."""
    checkpoint: dict[str, Any] = dict(video.temp_files_json or {})
    resolved = step or resolve_checkpoint_step(video)

    if video.tts_audio_path:
        checkpoint["audio_path"] = video.tts_audio_path
    if video.subtitle_ass_path:
        checkpoint["subtitle_path"] = video.subtitle_ass_path
    if video.selected_background_video:
        checkpoint["bg_video"] = video.selected_background_video
    if video.whisper_result_json:
        checkpoint["whisper_result"] = True
    if video.video_path and _video_file_valid(video.video_path):
        checkpoint["video_path"] = video.video_path

    checkpoint["step"] = resolved
    return checkpoint


def sanitize_video_checkpoint(video) -> dict[str, Any]:
    """Normalize temp_files_json on the video object; returns the checkpoint dict."""
    payload = build_checkpoint_payload(video)
    video.temp_files_json = payload
    return payload
