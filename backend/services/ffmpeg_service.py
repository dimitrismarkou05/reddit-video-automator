"""Core FFmpeg detection, installation, and management service."""

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from core.config import APP_DIR
from core.ffmpeg_settings import FFmpegSettings
from ffmpeg.detector import FfmpegDetector
from ffmpeg.installer import FfmpegInstaller, cancel_active_install

logger = logging.getLogger(__name__)


class FfmpegService:
    """Service for FFmpeg operations: detection, installation, path management."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = FFmpegSettings(db)
        self.detector = FfmpegDetector()

    def get_status(self) -> dict:
        """Get complete FFmpeg installation status.

        Priority:
        1. User-specified custom paths from settings
        2. App-local installation directory
        3. Auto-detected system paths
        """
        # Check saved custom paths first
        custom_ffmpeg = self.settings.get_ffmpeg_path()
        custom_ffprobe = self.settings.get_ffprobe_path()

        if custom_ffmpeg and custom_ffprobe:
            ffmpeg_ok = self._verify_binary(custom_ffmpeg)
            ffprobe_ok = self._verify_binary(custom_ffprobe)
            if ffmpeg_ok and ffprobe_ok:
                return self._finalize_status(
                    custom_ffmpeg, custom_ffprobe, ffmpeg_ok, ffprobe_ok
                )
            # Cached paths are stale (files were deleted). Clear them.
            self.settings.clear_all()

        # Check app-local installation
        app_ffmpeg = self._get_app_local_binary("ffmpeg")
        app_ffprobe = self._get_app_local_binary("ffprobe")
        if app_ffmpeg and app_ffprobe:
            ffmpeg_ok = self._verify_binary(app_ffmpeg)
            ffprobe_ok = self._verify_binary(app_ffprobe)
            if ffmpeg_ok and ffprobe_ok:
                return self._finalize_status(
                    app_ffmpeg, app_ffprobe, ffmpeg_ok, ffprobe_ok
                )

        # Auto-detect system-wide
        detected = self.detector.get_full_status()
        if detected["can_generate_videos"]:
            if detected["ffmpeg_path"]:
                self.settings.set_ffmpeg_path(detected["ffmpeg_path"])
            if detected["ffprobe_path"]:
                self.settings.set_ffprobe_path(detected["ffprobe_path"])
            if detected["ffmpeg_version"]:
                self.settings.set_ffmpeg_version(detected["ffmpeg_version"])
            if detected["ffprobe_version"]:
                self.settings.set_ffprobe_version(detected["ffprobe_version"])

        return detected

    def _finalize_status(
        self,
        ffmpeg_path: str,
        ffprobe_path: str,
        ffmpeg_ok: bool,
        ffprobe_ok: bool,
    ) -> dict:
        """Inject PATH and build a complete status dict."""
        if ffmpeg_ok and ffprobe_ok:
            self.detector._inject_to_path(ffmpeg_path, ffprobe_path)

        in_path = self.detector.is_in_path(ffmpeg_path) if ffmpeg_ok else False
        if ffmpeg_ok and ffprobe_ok and not in_path:
            logger.warning(
                "[FfmpegService] FFmpeg installed at %s but not resolvable on PATH",
                ffmpeg_path,
            )

        return {
            "ffmpeg_installed": ffmpeg_ok,
            "ffprobe_installed": ffprobe_ok,
            "ffmpeg_path": ffmpeg_path,
            "ffprobe_path": ffprobe_path,
            "ffmpeg_version": self._get_version(ffmpeg_path) if ffmpeg_ok else None,
            "ffprobe_version": self._get_version(ffprobe_path) if ffprobe_ok else None,
            "can_generate_videos": ffmpeg_ok and ffprobe_ok,
            "ffmpeg_in_path": in_path,
        }

    def set_custom_paths(self, ffmpeg_path: str, ffprobe_path: Optional[str] = None) -> dict:
        """Set custom FFmpeg/FFprobe paths and validate them."""
        ffmpeg_path = ffmpeg_path.strip()
        ffprobe_path = ffprobe_path.strip() if ffprobe_path else None

        # Validate ffmpeg
        if not self._verify_binary(ffmpeg_path):
            return {
                "valid": False,
                "error": f"FFmpeg binary not valid or not executable: {ffmpeg_path}",
            }

        # Derive ffprobe if not provided
        if not ffprobe_path:
            ffmpeg_dir = Path(ffmpeg_path).parent
            ffprobe_name = "ffprobe.exe" if self.detector.system == "windows" else "ffprobe"
            derived = ffmpeg_dir / ffprobe_name
            if derived.exists():
                ffprobe_path = str(derived)

        if not ffprobe_path or not self._verify_binary(ffprobe_path):
            return {
                "valid": False,
                "error": "FFprobe binary not found or not valid. Please provide both paths.",
            }

        # Save
        self.settings.set_ffmpeg_path(ffmpeg_path)
        self.settings.set_ffprobe_path(ffprobe_path)
        self.settings.set_ffmpeg_version(self._get_version(ffmpeg_path) or "")
        self.settings.set_ffprobe_version(self._get_version(ffprobe_path) or "")
        self.detector._inject_to_path(ffmpeg_path, ffprobe_path)

        return {
            "valid": True,
            "ffmpeg_version": self._get_version(ffmpeg_path),
            "ffprobe_version": self._get_version(ffprobe_path),
        }

    def check_path(self, path: str) -> dict:
        """Validate a single binary path."""
        path = path.strip()
        if not Path(path).exists():
            return {"valid": False, "error": "File does not exist."}

        is_ffprobe = "ffprobe" in Path(path).name.lower()
        ok = self._verify_binary(path)
        if not ok:
            return {"valid": False, "error": "Binary is not executable or returned an error."}

        return {
            "valid": True,
            "ffmpeg_version": self._get_version(path) if not is_ffprobe else None,
            "ffprobe_version": self._get_version(path) if is_ffprobe else None,
        }

    def reset_paths(self) -> dict:
        """Clear custom paths and re-detect."""
        self.settings.clear_all()
        return self.get_status()

    def install_sync(self) -> dict:
        """Download and install FFmpeg. Sync version for BackgroundTasks."""
        installer = FfmpegInstaller()
        result = installer.install()

        if result.get("success"):
            ffmpeg_path = result["ffmpeg_path"]
            ffprobe_path = result["ffprobe_path"]
            self.settings.set_ffmpeg_path(ffmpeg_path)
            self.settings.set_ffprobe_path(ffprobe_path)
            self.settings.set_ffmpeg_version(self._get_version(ffmpeg_path) or "")
            self.settings.set_ffprobe_version(self._get_version(ffprobe_path) or "")
            self.detector._inject_to_path(ffmpeg_path, ffprobe_path)

        return result

    async def install(self) -> dict:
        """Async wrapper for install_sync."""
        return await asyncio.to_thread(self.install_sync)

    def cancel_install(self) -> None:
        """Cancel an in-progress installation."""
        cancel_active_install()

    def _get_app_local_binary(self, name: str) -> Optional[str]:
        """Check the app-local ffmpeg directory for a binary."""
        binary_name = f"{name}.exe" if self.detector.system == "windows" else name
        candidate = APP_DIR / "ffmpeg" / binary_name
        if candidate.exists():
            return str(candidate)
        return None

    def _verify_binary(self, path: str) -> bool:
        try:
            result = subprocess.run(
                [path, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return result.returncode == 0 and "version" in result.stdout.lower()
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
            return False

    def _get_version(self, path: str) -> Optional[str]:
        try:
            result = subprocess.run(
                [path, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                first_line = result.stdout.splitlines()[0]
                parts = first_line.split()
                if len(parts) >= 3:
                    return parts[2]
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError, IndexError):
            pass
        return None
