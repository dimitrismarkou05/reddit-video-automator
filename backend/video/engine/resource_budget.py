"""Adaptive CPU/RAM budget for FFmpeg compositing (quality unchanged)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResourceBudget:
    ffmpeg_threads: int
    filter_threads: int
    segment_duration_sec: int
    use_single_pass: bool
    total_ram_gb: float


def _get_total_ram_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        return 8.0


def compute_resource_budget(
    audio_duration: float,
    ffmpeg_threads_override: int = 0,
) -> ResourceBudget:
    """Return thread/segment limits based on system resources."""
    ram_gb = _get_total_ram_gb()
    cpu = os.cpu_count() or 4

    if ram_gb <= 8:
        ffmpeg_threads = 2
        filter_threads = 2
        segment_duration = 120
        use_single_pass = audio_duration <= 300
    elif ram_gb <= 16:
        ffmpeg_threads = min(4, max(2, cpu // 2))
        filter_threads = 3
        segment_duration = 300
        use_single_pass = audio_duration <= 600
    else:
        ffmpeg_threads = min(8, max(2, cpu // 2))
        filter_threads = 4
        segment_duration = 600
        use_single_pass = True

    if ffmpeg_threads_override > 0:
        ffmpeg_threads = ffmpeg_threads_override

    budget = ResourceBudget(
        ffmpeg_threads=ffmpeg_threads,
        filter_threads=filter_threads,
        segment_duration_sec=segment_duration,
        use_single_pass=use_single_pass,
        total_ram_gb=round(ram_gb, 1),
    )
    logger.info(
        "[ResourceBudget] ram=%.1fGB threads=%d segment=%ds single_pass=%s",
        budget.total_ram_gb,
        budget.ffmpeg_threads,
        budget.segment_duration_sec,
        budget.use_single_pass,
    )
    return budget


def needs_segmentation(audio_duration: float, budget: ResourceBudget) -> bool:
    """True when compositing should run in time chunks to cap peak memory."""
    if audio_duration <= budget.segment_duration_sec:
        return False
    if budget.use_single_pass:
        return False
    return True


def segment_count(audio_duration: float, budget: ResourceBudget) -> int:
    """Number of segments for a segmented compose."""
    if not needs_segmentation(audio_duration, budget):
        return 1
    import math
    return max(1, math.ceil(audio_duration / budget.segment_duration_sec))
