"""Utility helpers for video generation."""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from config import FFMPEG_PATH, FFPROBE_PATH, TEMP_DIR, OUTPUT_DIR, VIDEO_FORMATS


def sanitize_filename(name: str) -> str:
    """Create a filesystem-safe directory/filename from a story title."""
    name = re.sub(r'[<>":/\\|?*]', "", name)
    name = re.sub(r"\s+", "_", name).strip("._")
    return name[:80] or "untitled"


def get_output_folder(story_title: str) -> Path:
    """Create and return output/storyname/ directory."""
    folder = OUTPUT_DIR / sanitize_filename(story_title)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def get_temp_folder(job_id: int) -> Path:
    """Create and return temp directory for a specific job."""
    folder = TEMP_DIR / f"job_{job_id}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def cleanup_temp(job_id: int) -> None:
    """Remove temp files for a job."""
    folder = TEMP_DIR / f"job_{job_id}"
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)


def find_ffmpeg() -> Optional[str]:
    """Auto-detect FFmpeg binary path."""
    return shutil.which("ffmpeg")


def find_ffprobe() -> Optional[str]:
    """Auto-detect FFprobe binary path."""
    return shutil.which("ffprobe")


def get_ffmpeg_version(path: str = FFMPEG_PATH) -> Optional[str]:
    """Get FFmpeg version string."""
    try:
        result = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.splitlines()[0]
    except Exception:
        pass
    return None


def get_video_info(path: str) -> Tuple[float, int, int]:
    """Return (duration_seconds, width, height) for a video file."""
    cmd = [
        FFPROBE_PATH,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration",
        "-of", "csv=p=0",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    parts = result.stdout.strip().split(",")
    width = int(parts[0])
    height = int(parts[1])
    duration = float(parts[2]) if len(parts) > 2 and parts[2] else 0.0
    return duration, width, height


def select_background_video(source_path: str) -> str:
    """
    If source_path is a directory, pick a random video file.
    If it's a file, return it directly.
    """
    path = Path(source_path)
    if path.is_file():
        return str(path)

    if path.is_dir():
        videos = [
            f for f in path.iterdir()
            if f.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv", ".webm")
        ]
        if not videos:
            raise ValueError(f"No video files found in directory: {source_path}")
        import random
        return str(random.choice(videos))

    raise ValueError(f"Invalid background source: {source_path}")


def calculate_target_dimensions(video_format: str) -> Tuple[int, int]:
    """Return (width, height) for the requested format."""
    fmt = VIDEO_FORMATS.get(video_format, VIDEO_FORMATS["shorts"])
    return fmt["width"], fmt["height"]


def format_duration(seconds: float) -> str:
    """Convert seconds to MM:SS format."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"
