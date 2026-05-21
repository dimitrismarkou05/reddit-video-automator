"""FFmpeg path storage and retrieval via SettingsManager."""

from typing import Optional
from sqlalchemy.orm import Session

from core.settings_manager import SettingsManager


class FFmpegSettings:
    """Manages FFmpeg/FFprobe path persistence in the settings database."""

    FFMPEG_PATH_KEY = "ffmpeg_path"
    FFPROBE_PATH_KEY = "ffprobe_path"
    FFMPEG_VERSION_KEY = "ffmpeg_version"
    FFPROBE_VERSION_KEY = "ffprobe_version"

    def __init__(self, db: Session):
        self._mgr = SettingsManager(db)

    def get_ffmpeg_path(self) -> Optional[str]:
        return self._mgr.get(self.FFMPEG_PATH_KEY)

    def set_ffmpeg_path(self, path: str) -> None:
        self._mgr.set(self.FFMPEG_PATH_KEY, path)

    def get_ffprobe_path(self) -> Optional[str]:
        return self._mgr.get(self.FFPROBE_PATH_KEY)

    def set_ffprobe_path(self, path: str) -> None:
        self._mgr.set(self.FFPROBE_PATH_KEY, path)

    def get_ffmpeg_version(self) -> Optional[str]:
        return self._mgr.get(self.FFMPEG_VERSION_KEY)

    def set_ffmpeg_version(self, version: str) -> None:
        self._mgr.set(self.FFMPEG_VERSION_KEY, version)

    def get_ffprobe_version(self) -> Optional[str]:
        return self._mgr.get(self.FFPROBE_VERSION_KEY)

    def set_ffprobe_version(self, version: str) -> None:
        self._mgr.set(self.FFPROBE_VERSION_KEY, version)

    def clear_all(self) -> None:
        """Remove all FFmpeg-related settings."""
        for key in (
            self.FFMPEG_PATH_KEY,
            self.FFPROBE_PATH_KEY,
            self.FFMPEG_VERSION_KEY,
            self.FFPROBE_VERSION_KEY,
        ):
            self._mgr.set(key, "")
