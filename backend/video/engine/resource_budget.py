"""Adaptive CPU/RAM budget for FFmpeg compositing (quality unchanged)."""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_LOW_RAM_AVAILABLE_GB = 3.5
_LOW_PRIORITY_AVAILABLE_GB = 2.0


def _single_pass_max_duration(available_gb: float) -> float:
    """Return the maximum audio duration (seconds) eligible for single-pass encoding.

    Scales with available RAM so machines with headroom skip the prepare+segment
    path entirely, saving ~2x encode work for long videos.  The original 1200 s
    cap is preserved for the 3.5–5 GB band (existing behavior unchanged there).
    """
    if available_gb >= 8.0:
        return 3600.0   # 60 min
    if available_gb >= 5.0:
        return 2400.0   # 40 min
    if available_gb >= _LOW_RAM_AVAILABLE_GB:
        return 1200.0   # 20 min — previous hard limit
    return 0.0          # segmented required (low-RAM safety)


@dataclass(frozen=True)
class ResourceBudget:
    ffmpeg_threads: int
    filter_threads: int
    segment_duration_sec: int
    use_single_pass: bool
    total_ram_gb: float
    available_ram_gb: float
    use_low_priority: bool


def get_memory_gb() -> tuple[float, float]:
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
    """Return thread/segment limits based on system resources (compose-only phase).

    When there is genuine RAM headroom (available ≥ 4 GB on a machine with
    more than 8 GB total) we pass ffmpeg_threads=0 so FFmpeg auto-selects the
    optimal count for frame threading.  On low-RAM machines the conservative
    caps remain in place to avoid OOM.  The user's ffmpeg_threads Settings
    override always wins.
    """
    total_gb, available_gb = get_memory_gb()
    cpu = os.cpu_count() or 4

    if total_gb <= 8:
        # Allow all available cores when RAM is comfortable; fall back to 4
        # when memory is tight to avoid OOM during encode.
        ffmpeg_threads = cpu if available_gb >= 3.0 else min(4, cpu)
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

    # On machines with healthy RAM and total > 8 GB, let FFmpeg (libx264 /
    # hardware encoders) auto-select the best thread count via frame threading.
    # Value 0 is valid for -threads and means "auto".
    if available_gb >= 4.0 and total_gb > 8 and ffmpeg_threads_override == 0:
        ffmpeg_threads = 0

    if ffmpeg_threads_override > 0:
        ffmpeg_threads = ffmpeg_threads_override

    # After ML models are evicted, prefer single pass when RAM and duration allow.
    use_single_pass = audio_duration <= _single_pass_max_duration(available_gb)

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


