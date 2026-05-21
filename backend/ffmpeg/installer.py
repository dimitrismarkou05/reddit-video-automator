"""FFmpeg download, extraction, and installation logic."""

import asyncio
import os
import platform
import random
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

    # Rotating user agents - same as Reddit client
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) Gecko/20100101 Firefox/126.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    ]

    def __init__(self, progress_callback: Optional[Callable[[dict], None]] = None):
        self.progress_callback = progress_callback
        self._cancelled = False
        self.system = platform.system().lower()
        self.ffmpeg_dir = APP_DIR / "ffmpeg"
        self.ffmpeg_dir.mkdir(parents=True, exist_ok=True)
        self._ua_index = 0

    def _next_ua(self) -> str:
        """Rotate through user agents."""
        ua = self.USER_AGENTS[self._ua_index % len(self.USER_AGENTS)]
        self._ua_index += 1
        return ua

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

            # Reset UA index for each mirror to try fresh user agents
            self._ua_index = mirror_idx * 3

            self._emit(
                "mirror_switch",
                step=f"Trying mirror {mirror_idx + 1}/{len(mirrors)}...",
                mirror=mirror_url,
                progress=0,
            )

            for attempt in range(1, 4):
                if self._cancelled:
                    self._emit("cancelled", step="Installation cancelled by user")
                    return {"success": False, "error": "Installation cancelled"}

                if attempt > 1:
                    self._emit(
                        "retry",
                        step=f"Retrying download (attempt {attempt}/3)...",
                        mirror=mirror_url,
                        retry=attempt,
                        progress=5,
                    )
                    # Exponential backoff with jitter
                    await asyncio.sleep(random.uniform(1, 2 ** attempt))

                try:
                    result = await self._download_and_install(mirror_url, attempt)
                    if result["success"]:
                        self._emit(
                            "complete",
                            progress=100,
                            step="Installation complete!",
                            mirror=mirror_url,
                        )
                        return result
                except Exception as exc:
                    error_msg = str(exc).lower()
                    
                    # Check error types for faster failover
                    is_404 = "404" in error_msg
                    is_403 = "403" in error_msg or "forbidden" in error_msg
                    is_timeout = any(x in error_msg for x in ["timeout", "timed out"])
                    is_connection = any(x in error_msg for x in ["connect", "connection", "network"])
                    
                    if is_404:
                        # URL doesn't exist, move to next mirror immediately
                        self._emit(
                            "mirror_switch",
                            step=f"Mirror URL not found, trying next...",
                            mirror=mirror_url,
                            error=error_msg,
                            progress=0,
                        )
                        break
                    elif is_403 and attempt == 1:
                        # Access denied, try different user agent on next attempt
                        self._emit(
                            "retry",
                            step=f"Access denied, trying with different user agent...",
                            mirror=mirror_url,
                            retry=attempt,
                            progress=5,
                        )
                        continue
                    elif (is_timeout or is_connection) and attempt == 1:
                        # Connection issue, try next mirror
                        self._emit(
                            "mirror_switch",
                            step=f"Connection issue, trying next mirror...",
                            mirror=mirror_url,
                            error=error_msg,
                            progress=0,
                        )
                        break
                    else:
                        self._emit(
                            "retry",
                            step=f"Download failed: {error_msg[:100]}",
                            mirror=mirror_url,
                            retry=attempt,
                            error=error_msg,
                            progress=5,
                        )
                        continue

        self._emit(
            "failed",
            step="All mirrors exhausted. Installation failed.",
            error="All download mirrors failed after retries. Please install FFmpeg manually.",
            progress=0,
        )
        return {
            "success": False,
            "error": "All download mirrors failed after retries. Please install FFmpeg manually.",
        }

    async def _download_and_install(self, url: str, attempt: int = 1) -> dict:
        """Download from a single mirror and install."""
        temp_dir = Path(tempfile.mkdtemp(dir=TEMP_DIR))
        archive_path = temp_dir / "ffmpeg_archive"

        try:
            # Step 1: Download - smooth progress from 0 to 60
            self._emit("download_progress", step="Connecting to mirror...", progress=5)

            # Rotate user agent on each attempt
            headers = {
                "User-Agent": self._next_ua(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "DNT": "1",
                "Upgrade-Insecure-Requests": "1",
            }

            # Longer timeout for slow connections
            timeout_config = httpx.Timeout(300.0, connect=30.0, read=120.0)
            
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=timeout_config,
                headers=headers,
                verify=True
            ) as client:
                self._emit("download_progress", step="Starting download...", progress=10)
                
                # Use stream() to download progressively
                async with client.stream("GET", url) as response:
                    # Handle different status codes
                    if response.status_code == 404:
                        raise Exception(f"HTTP 404 Not Found - URL may be invalid")
                    elif response.status_code == 403:
                        raise Exception(f"HTTP 403 Forbidden - Access denied with UA: {headers['User-Agent'][:50]}...")
                    elif response.status_code == 429:
                        raise Exception(f"HTTP 429 Too Many Requests - Rate limited")
                    
                    response.raise_for_status()
                    
                    total = int(response.headers.get("content-length", 0))
                    downloaded = 0
                    last_percent = 10
                    downloaded_mb_last = 0

                    with open(archive_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=262144):  # 256KB chunks for smoother updates
                            if self._cancelled:
                                raise asyncio.CancelledError("Installation cancelled")
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if total > 0:
                                percent = 10 + int((downloaded / total) * 50)
                                downloaded_mb = downloaded // (1024 * 1024)
                                
                                # Update progress when percentage changes OR every 5MB
                                if percent != last_percent or downloaded_mb > downloaded_mb_last + 5:
                                    last_percent = percent
                                    downloaded_mb_last = downloaded_mb
                                    total_mb = total // (1024 * 1024)
                                    self._emit(
                                        "download_progress",
                                        step=f"Downloading... {downloaded_mb}MB / {total_mb}MB",
                                        progress=percent,
                                    )

            self._emit("download_progress", step="Download complete!", progress=60)

            # Step 2: Extract - progress 60 to 75
            self._emit("extracting", step="Extracting archive...", progress=65)
            extract_dir = temp_dir / "extracted"
            extract_dir.mkdir()

            # Try different extraction methods based on file extension
            if archive_path.suffix == ".zip" or ".zip" in str(url):
                await asyncio.to_thread(self._extract_zip, archive_path, extract_dir)
            elif archive_path.suffix == ".xz" or ".tar." in str(url):
                await asyncio.to_thread(self._extract_tar, archive_path, extract_dir)
            else:
                # Try both
                try:
                    await asyncio.to_thread(self._extract_zip, archive_path, extract_dir)
                except Exception:
                    await asyncio.to_thread(self._extract_tar, archive_path, extract_dir)

            self._emit("extracting", step="Extraction complete", progress=75)

            # Step 3: Locate binaries - 75 to 85
            self._emit("installing", step="Locating binaries...", progress=80)
            ffmpeg_bin, ffprobe_bin = await asyncio.to_thread(
                self._find_binaries, extract_dir
            )

            if not ffmpeg_bin or not ffprobe_bin:
                raise RuntimeError(
                    f"Could not find ffmpeg and ffprobe binaries in the downloaded archive. "
                    f"Found ffmpeg: {ffmpeg_bin is not None}, ffprobe: {ffprobe_bin is not None}"
                )

            # Step 4: Install binaries - 85 to 95
            self._emit("installing", step="Installing binaries...", progress=85)
            dest_ffmpeg = self.ffmpeg_dir / ("ffmpeg.exe" if self.system == "windows" else "ffmpeg")
            dest_ffprobe = self.ffmpeg_dir / ("ffprobe.exe" if self.system == "windows" else "ffprobe")

            shutil.copy2(ffmpeg_bin, dest_ffmpeg)
            shutil.copy2(ffprobe_bin, dest_ffprobe)

            if self.system != "windows":
                os.chmod(dest_ffmpeg, 0o755)
                os.chmod(dest_ffprobe, 0o755)

            self._emit("installing", step="Verifying installation...", progress=95)

            # Step 5: Verify - FIXED to prevent hanging
            ffmpeg_ok = await asyncio.to_thread(self._verify_binary, str(dest_ffmpeg))
            ffprobe_ok = await asyncio.to_thread(self._verify_binary, str(dest_ffprobe))

            if not ffmpeg_ok or not ffprobe_ok:
                raise RuntimeError("Installed binaries failed verification.")

            return {
                "success": True,
                "ffmpeg_path": str(dest_ffmpeg),
                "ffprobe_path": str(dest_ffprobe),
            }

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise Exception(f"Installation failed: {exc}")
        finally:
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
        """Verify binary works with a short timeout and proper arguments."""
        try:
            # Use timeout=5 seconds to prevent hanging
            # Use -version with no interaction
            result = subprocess.run(
                [path, "-version"],
                capture_output=True,
                text=True,
                timeout=5,  # Reduced from 15 to 5 seconds
                check=False,
                stdin=subprocess.DEVNULL,  # Prevent waiting for input
            )
            # Check exit code and that we got some output
            valid = result.returncode == 0 and len(result.stdout) > 0
            
            if not valid and result.stderr:
                # Log stderr for debugging but don't fail if stdout has version info
                valid = "version" in result.stdout.lower() or "version" in result.stderr.lower()
            
            return valid
        except subprocess.TimeoutExpired:
            # If it times out, try killing the process
            return False
        except (OSError, FileNotFoundError):
            return False