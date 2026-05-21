from pathlib import Path

APP_NAME = "reddit-video-automator"
APP_DIR = Path.home() / f".{APP_NAME}"
APP_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{APP_DIR / 'app.db'}"
KEY_FILE = APP_DIR / ".key"

# Phase 2: Video output directories
OUTPUT_DIR = APP_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

TEMP_DIR = APP_DIR / "temp"
TEMP_DIR.mkdir(exist_ok=True)

# FFmpeg installation directory
FFMPEG_DIR = APP_DIR / "ffmpeg"
FFMPEG_DIR.mkdir(exist_ok=True)

# Default video dimensions
VIDEO_FORMATS = {
    "shorts": {"width": 1080, "height": 1920, "aspect": "9:16"},
    "normal": {"width": 1920, "height": 1080, "aspect": "16:9"},
}

DEFAULT_VIDEO_FORMAT = "shorts"

# FFmpeg binary path (auto-detected or overridden in settings)
FFMPEG_PATH = "ffmpeg"
FFPROBE_PATH = "ffprobe"
