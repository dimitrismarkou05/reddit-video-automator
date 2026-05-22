"""FFmpeg download, extraction, and installation logic."""

import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Optional, Callable, Dict, List

import requests

from core.config import APP_DIR, TEMP_DIR
from ffmpeg.mirrors import get_mirrors_for_system
from ffmpeg.sse import update_install_state


# Global active installer for cross-request cancellation
_active_installer: Optional["FfmpegInstaller"] = None
_installer_lock = threading.Lock()


def get_active_installer() -> Optional["FfmpegInstaller"]:
    return _active_installer


def cancel_active_install() -> None:
    """Cancel any in-progress installation."""
    global _active_installer
    with _installer_lock:
        installer = _active_installer
    if installer is not None:
        installer.cancel()


class FfmpegInstaller:
    """Handles downloading and installing FFmpeg/FFprobe. Sync-based for reliability."""

    def __init__(self, progress_callback: Optional[Callable[[dict], None]] = None):
        self.progress_callback = progress_callback
        self._cancelled = threading.Event()
        self._current_response: Optional[requests.Response] = None
        self.system = platform.system().lower()
        self.ffmpeg_dir = APP_DIR / "ffmpeg"
        self.ffmpeg_dir.mkdir(parents=True, exist_ok=True)

        # Register as active installer (cancels any previous)
        global _active_installer
        with _installer_lock:
            if _active_installer is not None and _active_installer is not self:
                _active_installer.cancel()
            _active_installer = self

    def cancel(self) -> None:
        """Signal cancellation and close any active HTTP connection."""
        self._cancelled.set()
        if self._current_response is not None:
            try:
                self._current_response.close()
            except Exception:
                pass

    def _emit(self, event_type: str, **kwargs) -> None:
        """Emit progress via both callback and global SSE state."""
        payload = {
            "event_type": event_type,
            "progress_percent": kwargs.get("progress", 0),
            "step": kwargs.get("step", ""),
            "mirror": kwargs.get("mirror"),
            "retry_count": kwargs.get("retry", 0),
            "error": kwargs.get("error"),
        }
        update_install_state(
            event_type=event_type,
            progress=kwargs.get("progress", 0),
            step=kwargs.get("step", ""),
            mirror=kwargs.get("mirror"),
            retry=kwargs.get("retry", 0),
            error=kwargs.get("error"),
        )
        if self.progress_callback:
            self.progress_callback(payload)

    def install(self) -> dict:
        """Download and install FFmpeg. Returns status dict."""
        mirrors = get_mirrors_for_system()
        if not mirrors:
            return {
                "success": False,
                "error": "No download mirrors available for this operating system.",
            }

        last_error = None

        for mirror_idx, mirror in enumerate(mirrors):
            if self._cancelled.is_set():
                self._emit("cancelled", step="Installation cancelled by user", progress=0)
                self._unregister()
                return {"success": False, "error": "Installation cancelled"}

            self._emit(
                "mirror_switch",
                step=f"Trying mirror {mirror_idx + 1}/{len(mirrors)}: {mirror['name']}",
                mirror=mirror["url"],
                progress=0,
            )

            for attempt in range(3):  # 3 attempts per mirror
                if self._cancelled.is_set():
                    self._emit("cancelled", step="Installation cancelled by user", progress=0)
                    self._unregister()
                    return {"success": False, "error": "Installation cancelled"}

                if attempt > 0:
                    self._emit(
                        "retry",
                        step=f"Retrying {mirror['name']} (attempt {attempt + 1}/3)...",
                        mirror=mirror["url"],
                        retry=attempt,
                        progress=5,
                    )
                    # Exponential backoff with jitter, max 10s
                    time.sleep(min(2 ** attempt + 0.5, 10))

                try:
                    result = self._download_and_install(mirror)
                    if result["success"]:
                        self._emit(
                            "complete",
                            progress=100,
                            step="Installation complete!",
                            mirror=mirror["url"],
                        )
                        self._unregister()
                        return result
                except Exception as exc:
                    error_msg = str(exc).lower()
                    last_error = str(exc)

                    is_404 = "404" in error_msg
                    is_403 = "403" in error_msg or "forbidden" in error_msg
                    is_timeout = any(x in error_msg for x in ["timeout", "timed out", "read timed out"])
                    is_connection = any(x in error_msg for x in ["connect", "connection", "network", "refused", "unreachable"])
                    is_cancelled = "cancel" in error_msg

                    if is_cancelled:
                        self._emit("cancelled", step="Installation cancelled by user", progress=0)
                        self._unregister()
                        return {"success": False, "error": "Installation cancelled"}

                    if is_404:
                        self._emit(
                            "mirror_switch",
                            step=f"Mirror not found ({mirror['name']}), trying next...",
                            mirror=mirror["url"],
                            error=last_error[:200],
                            progress=0,
                        )
                        break  # Move to next mirror immediately

                    elif is_403 and attempt == 0:
                        self._emit(
                            "retry",
                            step=f"Access denied on {mirror['name']}, retrying...",
                            mirror=mirror["url"],
                            retry=attempt + 1,
                            progress=5,
                        )
                        continue

                    elif (is_timeout or is_connection) and attempt < 2:
                        self._emit(
                            "retry",
                            step=f"Connection issue on {mirror['name']}: {last_error[:80]}",
                            mirror=mirror["url"],
                            retry=attempt + 1,
                            error=last_error[:200],
                            progress=5,
                        )
                        continue

                    else:
                        self._emit(
                            "retry",
                            step=f"Download failed from {mirror['name']}: {last_error[:80]}",
                            mirror=mirror["url"],
                            retry=attempt + 1,
                            error=last_error[:200],
                            progress=5,
                        )
                        continue

        self._emit(
            "failed",
            step="All mirrors exhausted. Installation failed.",
            error=last_error or "All download mirrors failed after retries. Please install FFmpeg manually.",
            progress=0,
        )
        self._unregister()
        return {
            "success": False,
            "error": last_error or "All download mirrors failed after retries. Please install FFmpeg manually.",
        }

    def _unregister(self) -> None:
        """Remove this installer from the global active slot."""
        global _active_installer
        with _installer_lock:
            if _active_installer is self:
                _active_installer = None

    def _download_and_install(self, mirror: Dict) -> dict:
        """Download from a single mirror and install."""
        url = mirror["url"]
        file_type = mirror.get("type", "zip")

        # Create temp directory
        temp_dir = Path(tempfile.mkdtemp(dir=TEMP_DIR))
        archive_path = temp_dir / f"ffmpeg_archive.{file_type.replace('.', '_')}"

        try:
            # Step 1: Download
            self._emit("download_progress", step="Connecting to mirror...", progress=5)

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
            }

            # Connect timeout 30s, read timeout 300s
            with requests.get(url, headers=headers, stream=True, timeout=(30, 300)) as response:
                self._current_response = response

                if response.status_code == 404:
                    raise Exception("HTTP 404 Not Found")
                elif response.status_code == 403:
                    raise Exception("HTTP 403 Forbidden")
                elif response.status_code == 429:
                    raise Exception("HTTP 429 Too Many Requests")
                elif response.status_code >= 500:
                    raise Exception(f"HTTP {response.status_code} Server Error")

                response.raise_for_status()

                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                last_percent = 5
                last_update_time = time.time()

                self._emit("download_progress", step="Starting download...", progress=10)

                with open(archive_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=262144):  # 256KB
                        if self._cancelled.is_set():
                            raise Exception("Installation cancelled")

                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            now = time.time()
                            if total > 0:
                                percent = 10 + int((downloaded / total) * 50)
                                if percent != last_percent or (now - last_update_time) > 0.5:
                                    last_percent = percent
                                    last_update_time = now
                                    downloaded_mb = downloaded / (1024 * 1024)
                                    total_mb = total / (1024 * 1024)
                                    self._emit(
                                        "download_progress",
                                        step=f"Downloading... {downloaded_mb:.1f}MB / {total_mb:.1f}MB",
                                        progress=percent,
                                    )
                            else:
                                # Unknown size: pulse progress based on chunks
                                if (now - last_update_time) > 1.0:
                                    last_update_time = now
                                    downloaded_mb = downloaded / (1024 * 1024)
                                    # Pulse between 10-55%
                                    pulse = 10 + (int(downloaded_mb) % 45)
                                    self._emit(
                                        "download_progress",
                                        step=f"Downloading... {downloaded_mb:.1f}MB",
                                        progress=pulse,
                                    )

                # Validate downloaded file
                if not archive_path.exists() or archive_path.stat().st_size == 0:
                    raise Exception("Download failed - empty or missing file")

                self._emit("download_progress", step="Download complete!", progress=60)

            # Step 2: Extract
            self._emit("extracting", step="Extracting archive...", progress=65)
            extract_dir = temp_dir / "extracted"
            extract_dir.mkdir()

            if file_type == "zip" or archive_path.suffix == ".zip":
                self._extract_zip(archive_path, extract_dir)
            elif file_type in ("tar.xz", "tar.gz") or ".tar." in str(archive_path):
                self._extract_tar(archive_path, extract_dir)
            else:
                # Try zip first, then tar
                try:
                    self._extract_zip(archive_path, extract_dir)
                except Exception:
                    self._extract_tar(archive_path, extract_dir)

            self._emit("extracting", step="Extraction complete", progress=75)

            # Step 3: Locate binaries
            self._emit("installing", step="Locating binaries...", progress=80)
            ffmpeg_bin, ffprobe_bin = self._find_binaries(extract_dir)

            if not ffmpeg_bin or not ffprobe_bin:
                raise RuntimeError(
                    f"Could not find ffmpeg and ffprobe binaries in archive. "
                    f"ffmpeg: {ffmpeg_bin is not None}, ffprobe: {ffprobe_bin is not None}"
                )

            # Step 4: Install binaries
            self._emit("installing", step="Installing binaries...", progress=85)
            dest_ffmpeg = self.ffmpeg_dir / ("ffmpeg.exe" if self.system == "windows" else "ffmpeg")
            dest_ffprobe = self.ffmpeg_dir / ("ffprobe.exe" if self.system == "windows" else "ffprobe")

            # Remove old binaries if they exist (prevents "file in use" on Windows)
            if dest_ffmpeg.exists():
                dest_ffmpeg.unlink()
            if dest_ffprobe.exists():
                dest_ffprobe.unlink()

            shutil.copy2(ffmpeg_bin, dest_ffmpeg)
            shutil.copy2(ffprobe_bin, dest_ffprobe)

            if self.system != "windows":
                os.chmod(dest_ffmpeg, 0o755)
                os.chmod(dest_ffprobe, 0o755)

            # Step 5: Verify
            self._emit("installing", step="Verifying installation...", progress=95)

            ffmpeg_ok = self._verify_binary(str(dest_ffmpeg))
            ffprobe_ok = self._verify_binary(str(dest_ffprobe))

            if not ffmpeg_ok or not ffprobe_ok:
                # Cleanup on verification failure
                if dest_ffmpeg.exists():
                    dest_ffmpeg.unlink()
                if dest_ffprobe.exists():
                    dest_ffprobe.unlink()
                raise RuntimeError(
                    f"Verification failed. ffmpeg: {ffmpeg_ok}, ffprobe: {ffprobe_ok}"
                )

            return {
                "success": True,
                "ffmpeg_path": str(dest_ffmpeg),
                "ffprobe_path": str(dest_ffprobe),
            }

        except Exception as exc:
            raise Exception(f"Installation failed: {exc}")
        finally:
            self._current_response = None
            # Always cleanup temp directory
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _extract_zip(self, archive: Path, dest: Path) -> None:
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(dest)

    def _extract_tar(self, archive: Path, dest: Path) -> None:
        with tarfile.open(archive, "r:*") as tf:
            tf.extractall(dest)

    def _find_binaries(self, root: Path) -> tuple[Optional[Path], Optional[Path]]:
        """Recursively find ffmpeg and ffprobe binaries in extracted archive."""
        ffmpeg_name = "ffmpeg.exe" if self.system == "windows" else "ffmpeg"
        ffprobe_name = "ffprobe.exe" if self.system == "windows" else "ffprobe"

        ffmpeg_path: Optional[Path] = None
        ffprobe_path: Optional[Path] = None

        for path in root.rglob("*"):
            if path.is_file():
                name = path.name.lower()
                if name == ffmpeg_name:
                    ffmpeg_path = path
                elif name == ffprobe_name:
                    ffprobe_path = path

            if ffmpeg_path and ffprobe_path:
                break

        return ffmpeg_path, ffprobe_path

    def _verify_binary(self, path: str) -> bool:
        """Verify binary works with a proper timeout."""
        try:
            result = subprocess.run(
                [path, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                stdin=subprocess.DEVNULL,
            )
            valid = result.returncode == 0 and len(result.stdout) > 0
            if not valid:
                valid = "version" in result.stdout.lower() or "version" in result.stderr.lower()
            return valid
        except subprocess.TimeoutExpired:
            return False
        except (OSError, FileNotFoundError):
            return False
