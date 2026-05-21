"""FFmpeg download, extraction, and installation logic."""

import asyncio
import os
import platform
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Callable

import httpx

from core.config import APP_DIR, TEMP_DIR
from ffmpeg.mirrors import get_mirror_urls
from ffmpeg.sse import update_install_state


class FfmpegInstaller:
    """Handles downloading and installing FFmpeg/FFprobe."""

    def __init__(self, progress_callback: Optional[Callable[[dict], None]] = None):
        self.progress_callback = progress_callback
        self._cancelled = False
        self.system = platform.system().lower()
        self.ffmpeg_dir = APP_DIR / "ffmpeg"
        self.ffmpeg_dir.mkdir(parents=True, exist_ok=True)

    def cancel(self) -> None:
        self._cancelled = True

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
        # Update global SSE state (thread-safe via GIL)
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


    async def install(self) -> dict:
        """Download and install FFmpeg. Returns status dict."""
        mirrors = get_mirror_urls()
        if not mirrors:
            return {
                "success": False,
                "error": "No download mirrors available for this operating system.",
            }

        for mirror_idx, mirror_url in enumerate(mirrors):
            if self._cancelled:
                self._emit("cancelled", step="Installation cancelled by user")
                return {"success": False, "error": "Installation cancelled"}

            self._emit(
                "mirror_switch",
                step=f"Trying mirror {mirror_idx + 1}/{len(mirrors)}...",
                mirror=mirror_url,
            )

            for attempt in range(1, 4):  # 3 retries per mirror
                if self._cancelled:
                    self._emit("cancelled", step="Installation cancelled by user")
                    return {"success": False, "error": "Installation cancelled"}

                if attempt > 1:
                    self._emit(
                        "retry",
                        step=f"Retrying download (attempt {attempt}/3)...",
                        mirror=mirror_url,
                        retry=attempt,
                    )
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

                try:
                    result = await self._download_and_install(mirror_url)
                    if result["success"]:
                        self._emit(
                            "complete",
                            progress=100,
                            step="Installation complete!",
                            mirror=mirror_url,
                        )
                        return result
                except Exception as exc:
                    error_msg = str(exc)
                    self._emit(
                        "retry",
                        step=f"Download failed: {error_msg}",
                        mirror=mirror_url,
                        retry=attempt,
                        error=error_msg,
                    )
                    continue

        self._emit(
            "failed",
            step="All mirrors exhausted. Installation failed.",
            error="All download mirrors failed after retries.",
        )
        return {
            "success": False,
            "error": "All download mirrors failed after retries. Please install FFmpeg manually.",
        }

    async def _download_and_install(self, url: str) -> dict:
        """Download from a single mirror and install."""
        temp_dir = Path(tempfile.mkdtemp(dir=TEMP_DIR))
        archive_path = temp_dir / "ffmpeg_archive"

        try:
            # Download with progress
            self._emit("download_progress", step="Downloading FFmpeg...", progress=0)

            async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    total = int(response.headers.get("content-length", 0))
                    downloaded = 0

                    with open(archive_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            if self._cancelled:
                                raise asyncio.CancelledError("Installation cancelled")
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                percent = int((downloaded / total) * 50)
                                self._emit(
                                    "download_progress",
                                    step="Downloading FFmpeg...",
                                    progress=percent,
                                )

            self._emit("download_progress", step="Download complete", progress=50)

            # Extract
            self._emit("extracting", step="Extracting archive...", progress=55)
            extract_dir = temp_dir / "extracted"
            extract_dir.mkdir()

            if url.endswith(".zip") or str(archive_path).endswith(".zip"):
                await asyncio.to_thread(self._extract_zip, archive_path, extract_dir)
            elif url.endswith(".tar.xz") or ".tar." in url:
                await asyncio.to_thread(self._extract_tar, archive_path, extract_dir)
            else:
                # Try zip first, then tar
                try:
                    await asyncio.to_thread(self._extract_zip, archive_path, extract_dir)
                except Exception:
                    await asyncio.to_thread(self._extract_tar, archive_path, extract_dir)

            self._emit("extracting", step="Extraction complete", progress=75)

            # Find binaries
            self._emit("installing", step="Locating binaries...", progress=80)
            ffmpeg_bin, ffprobe_bin = await asyncio.to_thread(
                self._find_binaries, extract_dir
            )

            if not ffmpeg_bin or not ffprobe_bin:
                raise RuntimeError(
                    "Could not find ffmpeg and ffprobe binaries in the downloaded archive."
                )

            # Install (copy to app dir)
            self._emit("installing", step="Installing binaries...", progress=85)
            dest_ffmpeg = self.ffmpeg_dir / ("ffmpeg.exe" if self.system == "windows" else "ffmpeg")
            dest_ffprobe = self.ffmpeg_dir / ("ffprobe.exe" if self.system == "windows" else "ffprobe")

            shutil.copy2(ffmpeg_bin, dest_ffmpeg)
            shutil.copy2(ffprobe_bin, dest_ffprobe)

            # Make executable on Unix
            if self.system != "windows":
                os.chmod(dest_ffmpeg, 0o755)
                os.chmod(dest_ffprobe, 0o755)

            self._emit("installing", step="Verifying installation...", progress=95)

            # Verify
            ffmpeg_ok = await asyncio.to_thread(self._verify_binary, str(dest_ffmpeg))
            ffprobe_ok = await asyncio.to_thread(self._verify_binary, str(dest_ffprobe))

            if not ffmpeg_ok or not ffprobe_ok:
                raise RuntimeError("Installed binaries failed verification.")

            return {
                "success": True,
                "ffmpeg_path": str(dest_ffmpeg),
                "ffprobe_path": str(dest_ffprobe),
            }

        finally:
            # Cleanup temp files
            await asyncio.to_thread(shutil.rmtree, temp_dir, ignore_errors=True)

    def _extract_zip(self, archive: Path, dest: Path) -> None:
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(dest)

    def _extract_tar(self, archive: Path, dest: Path) -> None:
        import tarfile
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
        try:
            result = subprocess.run(
                [path, "-version"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False
