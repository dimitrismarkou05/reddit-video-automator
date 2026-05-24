"""Local TTS model installation logic using Coqui TTS auto-download.

DEPRECATED: The old zip-download approach is broken. Coqui TTS now
auto-downloads models via `TTS(model_name=...)` on first use.

This installer now triggers model download by initializing TTS with
the target model, which causes Coqui to fetch it automatically.
"""

import json
import shutil
import threading
import time
from pathlib import Path
from typing import Optional, Callable, Dict, List

from tts_local.sse import update_install_state
from tts_local.mirrors import get_default_model_name, get_available_models

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
    """Handles downloading TTS models via Coqui TTS auto-download."""

    def __init__(
        self,
        voice_name: str = "default",
        progress_callback: Optional[Callable[[dict], None]] = None,
    ):
        self.voice_name = voice_name
        self.progress_callback = progress_callback
        self._cancelled = threading.Event()

        global _active_installer
        with _installer_lock:
            if _active_installer is not None and _active_installer is not self:
                _active_installer.cancel()
            _active_installer = self

    def cancel(self) -> None:
        self._cancelled.set()

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
        """Download and install TTS model via Coqui auto-download."""
        try:
            import TTS
        except ImportError:
            self._emit(
                "failed",
                step="TTS package not installed",
                error="pip install TTS is required. Run: pip install TTS",
                progress=0,
            )
            self._unregister()
            return {
                "success": False,
                "error": "TTS Python package not installed. Run: pip install TTS",
            }

        required_mb = 500
        from core.config import APP_DIR
        free_mb = shutil.disk_usage(APP_DIR).free // (1024 * 1024)
        if free_mb < required_mb:
            self._emit(
                "failed",
                step="Insufficient disk space",
                error=f"Need {required_mb}MB free, have {free_mb}MB.",
                progress=0,
            )
            self._unregister()
            return {
                "success": False,
                "error": f"Insufficient disk space. Need {required_mb}MB free, have {free_mb}MB.",
            }

        models = get_available_models()
        model = next((m for m in models if m["id"] == self.voice_name), None)
        if not model:
            model = next((m for m in models if m["id"] == "en_ljspeech_tacotron2_ddc"), None)
        if not model:
            model_name = get_default_model_name()
            model = {
                "id": "en_ljspeech_tacotron2_ddc",
                "name": "English (LJSpeech) – Tacotron2 DDC",
                "model_name": model_name,
            }

        self._emit(
            "mirror_switch",
            step=f"Downloading {model['name']} via Coqui TTS...",
            mirror="coqui-tts-auto",
            progress=10,
        )

        try:
            self._emit("download_progress", step="Initializing TTS engine...", progress=20)

            from TTS.api import TTS

            self._emit("download_progress", step=f"Downloading {model['model_name']}...", progress=30)

            tts = TTS(model_name=model["model_name"], progress_bar=False, gpu=False)

            if self._cancelled.is_set():
                self._emit("cancelled", step="Installation cancelled by user", progress=0)
                self._unregister()
                return {"success": False, "error": "Installation cancelled"}

            self._emit("extracting", step="Model downloaded and cached", progress=70)

            self._emit("installing", step="Verifying model...", progress=85)

            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                tts.tts_to_file(text="Test.", file_path=tmp.name)

            self._emit(
                "complete",
                progress=100,
                step="Installation complete!",
                mirror="coqui-tts-auto",
            )
            self._unregister()
            return {
                "success": True,
                "voice_name": self.voice_name,
                "model_name": model["model_name"],
                "voice_path": None,
            }

        except Exception as exc:
            error_msg = str(exc)
            is_cancelled = "cancel" in error_msg.lower()

            if is_cancelled or self._cancelled.is_set():
                self._emit("cancelled", step="Installation cancelled by user", progress=0)
                self._unregister()
                return {"success": False, "error": "Installation cancelled"}

            self._emit(
                "failed",
                step="Installation failed",
                error=error_msg[:500],
                progress=0,
            )
            self._unregister()
            return {
                "success": False,
                "error": f"TTS model download failed: {error_msg}",
            }

    def _unregister(self) -> None:
        global _active_installer
        with _installer_lock:
            if _active_installer is self:
                _active_installer = None
