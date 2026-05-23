"""Utility helpers for video generation."""

import os
import re
import shutil
import subprocess
import random
import json
from pathlib import Path
from typing import Optional, Tuple, Dict, List

from core.config import FFMPEG_PATH, FFPROBE_PATH, TEMP_DIR, OUTPUT_DIR, VIDEO_FORMATS


def sanitize_filename(name: str) -> str:
    """Create a filesystem-safe directory/filename from a story title."""
    try:
        from slugify import slugify
        result = slugify(name, max_length=80, word_boundary=True)
        if not result:
            return "untitled"
        return result
    except ImportError:
        # Fallback if python-slugify not installed
        name = re.sub(r'[<>:"/\\|?*]', "", name)
        name = re.sub(r'\s+', "_", name).strip("._")
        name = re.sub(r'[^\w\-_.]', "", name)
        return name[:80] or "untitled"


def get_output_folder(story_id: int, story_title: str = "") -> Path:
    """Create and return output/{story_id}_{slug}/ directory."""
    slug = sanitize_filename(story_title) if story_title else str(story_id)
    folder = OUTPUT_DIR / f"{story_id}_{slug}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def get_temp_folder(video_id: int) -> Path:
    """Create and return temp directory for a specific video job."""
    folder = TEMP_DIR / f"video_{video_id}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def cleanup_temp(video_id: int, only_on_done: bool = False) -> None:
    """Remove temp files for a video job.

    If only_on_done is True, only cleanup when video is fully complete.
    """
    folder = TEMP_DIR / f"video_{video_id}"
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


# Cache for validated background videos
_validated_videos_cache: Dict[str, List[str]] = {}


def validate_video_with_ffprobe(path: str) -> bool:
    """Validate that a video file is readable by ffprobe."""
    try:
        result = subprocess.run(
            [FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0 and float(result.stdout.strip()) > 0
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return False


def select_background_video(source_path: str) -> str:
    """
    If source_path is a directory, pick a random video file.
    If it's a file, return it directly.

    Validates videos with ffprobe on first use and caches valid ones.
    Skips corrupt files automatically.
    """
    path = Path(source_path)
    if path.is_file():
        if not validate_video_with_ffprobe(str(path)):
            raise ValueError(f"Background video is corrupt or unreadable: {source_path}")
        return str(path)

    if path.is_dir():
        cache_key = str(path.resolve())
        if cache_key in _validated_videos_cache:
            valid_videos = _validated_videos_cache[cache_key]
            if valid_videos:
                return random.choice(valid_videos)
            raise ValueError(f"No valid video files in directory: {source_path}")

        videos = [
            f for f in path.iterdir()
            if f.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv", ".webm")
        ]
        if not videos:
            raise ValueError(f"No video files found in directory: {source_path}")

        # Validate each video and cache results
        valid_videos = []
        for v in videos:
            if validate_video_with_ffprobe(str(v)):
                valid_videos.append(str(v))

        _validated_videos_cache[cache_key] = valid_videos

        if not valid_videos:
            raise ValueError(f"No valid (non-corrupt) video files in directory: {source_path}")

        return random.choice(valid_videos)

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


def get_audio_duration(path: str) -> float:
    """Get audio duration using mutagen (pure-Python) without ffprobe."""
    try:
        from mutagen.mp3 import MP3
        audio = MP3(path)
        return audio.info.length
    except Exception:
        pass

    try:
        from mutagen import File
        audio = File(path)
        if audio and audio.info:
            return audio.info.length
    except Exception:
        pass

    # Final fallback to ffprobe
    try:
        result = subprocess.run(
            [FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception:
        pass

    raise RuntimeError(f"Could not determine duration for: {path}")
