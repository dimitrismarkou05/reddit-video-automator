"""Adaptive CPU/RAM budget for FFmpeg compositing (quality unchanged)."""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_PREP_BACKGROUND_MIN_DURATION = 60.0
_SINGLE_PASS_MAX_DURATION = 1200.0  # 20 minutes
_LOW_RAM_AVAILABLE_GB = 3.5
_LOW_PRIORITY_AVAILABLE_GB = 2.0


@dataclass(frozen=True)
class ResourceBudget:
    ffmpeg_threads: int
    filter_threads: int
    segment_duration_sec: int
    use_single_pass: bool
    total_ram_gb: float
    available_ram_gb: float
    use_low_priority: bool


def _get_memory_gb() -> tuple[float, float]:
    """Return (total_gb, available_gb)."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        return mem.total / (1024 ** 3), mem.available / (1024 ** 3)
    except Exception:
        return 8.0, 3.0


def compute_resource_budget(
    audio_duration: float,
    ffmpeg_threads_override: int = 0,
) -> ResourceBudget:
    """Return thread/segment limits based on system resources (compose-only phase)."""
    total_gb, available_gb = _get_memory_gb()
    cpu = os.cpu_count() or 4

    if total_gb <= 8:
        ffmpeg_threads = 4
        filter_threads = 2
        segment_duration = 180
    elif total_gb <= 16:
        ffmpeg_threads = min(4, max(2, cpu // 2))
        filter_threads = 3
        segment_duration = 300
    else:
        ffmpeg_threads = min(8, max(2, cpu // 2))
        filter_threads = 4
        segment_duration = 600

    if ffmpeg_threads_override > 0:
        ffmpeg_threads = ffmpeg_threads_override

    # After ML models are evicted, prefer single pass when RAM and duration allow.
    use_single_pass = (
        available_gb >= _LOW_RAM_AVAILABLE_GB
        and audio_duration <= _SINGLE_PASS_MAX_DURATION
    )

    use_low_priority = available_gb < _LOW_PRIORITY_AVAILABLE_GB

    budget = ResourceBudget(
        ffmpeg_threads=ffmpeg_threads,
        filter_threads=filter_threads,
        segment_duration_sec=segment_duration,
        use_single_pass=use_single_pass,
        total_ram_gb=round(total_gb, 1),
        available_ram_gb=round(available_gb, 1),
        use_low_priority=use_low_priority,
    )

    strategy = "single_pass" if use_single_pass else f"segmented×{segment_duration}s"
    logger.info(
        "[ResourceBudget] total=%.1fGB available=%.1fGB threads=%d strategy=%s",
        budget.total_ram_gb,
        budget.available_ram_gb,
        budget.ffmpeg_threads,
        strategy,
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
    return max(1, math.ceil(audio_duration / budget.segment_duration_sec))


def should_prepare_background(audio_duration: float) -> bool:
    """Pre-render looped/scaled background once for longer videos."""
    return audio_duration > _PREP_BACKGROUND_MIN_DURATION
