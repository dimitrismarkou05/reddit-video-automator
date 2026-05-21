"""FFmpeg/FFprobe system detection logic."""

import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from core.config import APP_DIR


class FfmpegDetector:
    """Detects FFmpeg and FFprobe binaries on the system."""

    def __init__(self):
        self.system = platform.system().lower()

    def _get_search_paths(self) -> list[Path]:
        """Return common installation paths for the current OS."""
        paths: list[Path] = []

        if self.system == "windows":
            paths.extend([
                Path(r"C:\ffmpeg\bin"),
                Path(r"C:\Program Files\ffmpeg\bin"),
                Path(r"C:\Program Files (x86)\ffmpeg\bin"),
                Path.home() / "ffmpeg" / "bin",
                APP_DIR / "ffmpeg",
            ])
        elif self.system == "darwin":
            paths.extend([
                Path("/usr/local/bin"),
                Path("/opt/homebrew/bin"),
                Path("/usr/bin"),
                APP_DIR / "ffmpeg",
                Path.home() / "ffmpeg",
            ])
        else:  # linux
            paths.extend([
                Path("/usr/bin"),
                Path("/usr/local/bin"),
                Path("/bin"),
                APP_DIR / "ffmpeg",
                Path.home() / ".local" / "bin",
                Path.home() / "ffmpeg",
            ])

        return paths

    def _test_binary(self, path: str, is_ffprobe: bool = False) -> bool:
        """Verify a binary is executable and returns version info."""
        try:
            cmd = [path, "-version"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return result.returncode == 0 and "version" in result.stdout.lower()
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
            return False

    def _get_version(self, path: str) -> Optional[str]:
        """Extract version string from binary."""
        try:
            result = subprocess.run(
                [path, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                # First line: "ffmpeg version 6.0" or "ffprobe version 6.0"
                first_line = result.stdout.splitlines()[0]
                parts = first_line.split()
                if len(parts) >= 3:
                    return parts[2]
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError, IndexError):
            pass
        return None

    def detect_ffmpeg(self) -> Optional[str]:
        """Search for ffmpeg binary. Returns full path or None."""
        # Check PATH first
        which = shutil.which("ffmpeg")
        if which and self._test_binary(which):
            return which

        # Check common paths
        for search_path in self._get_search_paths():
            binary_name = "ffmpeg.exe" if self.system == "windows" else "ffmpeg"
            candidate = search_path / binary_name
            if candidate.exists() and self._test_binary(str(candidate)):
                return str(candidate)

        return None

    def detect_ffprobe(self, ffmpeg_path: Optional[str] = None) -> Optional[str]:
        """Search for ffprobe binary. If ffmpeg_path is known, derive ffprobe from same dir."""
        if ffmpeg_path:
            ffmpeg_dir = Path(ffmpeg_path).parent
            binary_name = "ffprobe.exe" if self.system == "windows" else "ffprobe"
            sibling = ffmpeg_dir / binary_name
            if sibling.exists() and self._test_binary(str(sibling), is_ffprobe=True):
                return str(sibling)

        # Check PATH
        which = shutil.which("ffprobe")
        if which and self._test_binary(which, is_ffprobe=True):
            return which

        # Check common paths
        for search_path in self._get_search_paths():
            binary_name = "ffprobe.exe" if self.system == "windows" else "ffprobe"
            candidate = search_path / binary_name
            if candidate.exists() and self._test_binary(str(candidate), is_ffprobe=True):
                return str(candidate)

        return None

    def get_full_status(self) -> dict:
        """Return complete detection status."""
        ffmpeg_path = self.detect_ffmpeg()
        ffprobe_path = self.detect_ffprobe(ffmpeg_path)

        ffmpeg_ok = ffmpeg_path is not None
        ffprobe_ok = ffprobe_path is not None

        return {
            "ffmpeg_installed": ffmpeg_ok,
            "ffprobe_installed": ffprobe_ok,
            "ffmpeg_path": ffmpeg_path,
            "ffprobe_path": ffprobe_path,
            "ffmpeg_version": self._get_version(ffmpeg_path) if ffmpeg_ok else None,
            "ffprobe_version": self._get_version(ffprobe_path) if ffprobe_ok else None,
            "can_generate_videos": ffmpeg_ok and ffprobe_ok,
        }
