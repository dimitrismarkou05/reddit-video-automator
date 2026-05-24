"""Local TTS model download, extraction, and installation logic."""

import json
import shutil
import threading
import time
import zipfile
import tempfile
from pathlib import Path
from typing import Optional, Callable, Dict, List

import requests

from core.config import APP_DIR, TEMP_DIR, TTS_MODELS_DIR
from tts_local.mirrors import get_mirrors
from tts_local.sse import update_install_state

_active_installer: Optional["TtsModelInstaller"] = None
_installer_lock = threading.Lock()


def get_active_installer() -> Optional["TtsModelInstaller"]:
    return _active_installer


def cancel_active_install() -> None:
    global _active_installer
    with _installer_lock:
        installer = _active_installer
    if installer is not None:
        installer.cancel()


class TtsModelInstaller:
    """Handles downloading and installing a local TTS voice model package."""

    def __init__(
        self,
        voice_name: str = "default",
        progress_callback: Optional[Callable[[dict], None]] = None,
    ):
        self.voice_name = voice_name
        self.progress_callback = progress_callback
        self._cancelled = threading.Event()
        self._current_response: Optional[requests.Response] = None

        global _active_installer
        with _installer_lock:
            if _active_installer is not None and _active_installer is not self:
                _active_installer.cancel()
            _active_installer = self

    def cancel(self) -> None:
        self._cancelled.set()
        if self._current_response is not None:
            try:
                self._current_response.close()
            except Exception:
                pass

    def _emit(self, event_type: str, **kwargs) -> None:
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
        required_mb = 500
        free_mb = shutil.disk_usage(APP_DIR).free // (1024 * 1024)
        if free_mb < required_mb:
            return {
                "success": False,
                "error": f"Insufficient disk space. Need {required_mb}MB free, have {free_mb}MB.",
            }

        mirrors = get_mirrors()
        if not mirrors:
            return {"success": False, "error": "No download mirrors available."}

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

            for attempt in range(3):
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
                        break

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
            error=last_error or "All download mirrors failed after retries.",
            progress=0,
        )
        self._unregister()
        return {
            "success": False,
            "error": last_error or "All download mirrors failed after retries.",
        }

    def _unregister(self) -> None:
        global _active_installer
        with _installer_lock:
            if _active_installer is self:
                _active_installer = None

    def _download_and_install(self, mirror: Dict) -> dict:
        url = mirror["url"]
        file_type = mirror.get("type", "zip")
        temp_dir = None

        try:
            TEMP_DIR.mkdir(parents=True, exist_ok=True)
            TTS_MODELS_DIR.mkdir(parents=True, exist_ok=True)

            temp_dir = Path(tempfile.mkdtemp(dir=TEMP_DIR))
            archive_path = temp_dir / f"tts_model.{file_type.replace('.', '_')}"

            self._emit("download_progress", step="Connecting to mirror...", progress=5)

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }

            with requests.get(url, headers=headers, stream=True, timeout=(30, 300)) as response:
                self._current_response = response

                if response.status_code == 404:
                    raise Exception("HTTP 404 Not Found")
                elif response.status_code == 403:
                    raise Exception("HTTP 403 Forbidden")
                elif response.status_code >= 500:
                    raise Exception(f"HTTP {response.status_code} Server Error")

                response.raise_for_status()

                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                last_percent = 5
                last_update_time = time.time()

                self._emit("download_progress", step="Starting download...", progress=10)

                with open(archive_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=262144):
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
                                if (now - last_update_time) > 1.0:
                                    last_update_time = now
                                    downloaded_mb = downloaded / (1024 * 1024)
                                    pulse = 10 + (int(downloaded_mb) % 45)
                                    self._emit(
                                        "download_progress",
                                        step=f"Downloading... {downloaded_mb:.1f}MB",
                                        progress=pulse,
                                    )

                if not archive_path.exists() or archive_path.stat().st_size == 0:
                    raise Exception("Download failed - empty or missing file")

                self._emit("download_progress", step="Download complete!", progress=60)

            self._emit("extracting", step="Extracting archive...", progress=65)
            extract_dir = temp_dir / "extracted"
            extract_dir.mkdir()

            if file_type == "zip" or archive_path.suffix == ".zip":
                with zipfile.ZipFile(archive_path, "r") as zf:
                    zf.extractall(extract_dir)

            self._emit("extracting", step="Extraction complete", progress=75)

            self._emit("installing", step="Locating model files...", progress=80)
            voice_dir = TTS_MODELS_DIR / self.voice_name
            if voice_dir.exists():
                shutil.rmtree(voice_dir)
            voice_dir.mkdir(parents=True, exist_ok=True)

            config_found = False
            model_found = False

            for path in extract_dir.rglob("*"):
                if path.is_file():
                    dest = voice_dir / path.name
                    shutil.copy2(path, dest)
                    if path.name == "config.json":
                        config_found = True
                    if path.suffix in (".pth", ".onnx"):
                        model_found = True

            if not config_found or not model_found:
                shutil.rmtree(voice_dir, ignore_errors=True)
                raise RuntimeError(
                    f"Model files not found in archive. config: {config_found}, model: {model_found}"
                )

            self._emit("installing", step="Verifying installation...", progress=95)

            config_path = voice_dir / "config.json"
            with open(config_path, "r") as f:
                json.load(f)

            return {
                "success": True,
                "voice_name": self.voice_name,
                "voice_path": str(voice_dir),
            }

        except Exception as exc:
            raise Exception(f"Installation failed: {exc}")
        finally:
            self._current_response = None
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)