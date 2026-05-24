"""Local TTS model detection logic using Coqui TTS API.

Models are auto-managed by Coqui TTS via pip. We detect which models
have been downloaded by querying TTS().list_models() and checking
local cache directories.
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Optional

from core.config import TTS_MODELS_DIR


class TtsDetector:
    """Detects installed local TTS voice models via Coqui TTS API."""

    def __init__(self):
        self._models_cache: Optional[List[Dict]] = None

    def _get_tts_manager(self):
        """Lazy import TTS ModelManager."""
        try:
            from TTS.utils.manage import ModelManager
            return ModelManager()
        except Exception:
            return None

    def _list_downloaded_models(self) -> List[str]:
        """Return list of model names that have been downloaded locally."""
        manager = self._get_tts_manager()
        if not manager:
            return []

        try:
            from TTS.utils.generic_utils import get_user_data_dir
            tts_dir = Path(get_user_data_dir("tts"))

            downloaded = []
            if tts_dir.exists():
                for model_type_dir in tts_dir.iterdir():
                    if not model_type_dir.is_dir():
                        continue
                    for lang_dir in model_type_dir.iterdir():
                        if not lang_dir.is_dir():
                            continue
                        for dataset_dir in lang_dir.iterdir():
                            if not dataset_dir.is_dir():
                                continue
                            for model_dir in dataset_dir.iterdir():
                                if not model_dir.is_dir():
                                    continue
                                model_files = list(model_dir.glob("*.pth")) + list(model_dir.glob("*.onnx"))
                                config_file = model_dir / "config.json"
                                if model_files and config_file.exists():
                                    model_name = f"{model_type_dir.name}/{lang_dir.name}/{dataset_dir.name}/{model_dir.name}"
                                    downloaded.append(model_name)
            return downloaded
        except Exception:
            return []

    def detect_voices(self) -> List[Dict]:
        """Return list of available/downloaded voice models."""
        voices: List[Dict] = []

        downloaded = self._list_downloaded_models()

        from tts_local.mirrors import get_available_models
        available = get_available_models()

        for model in available:
            is_downloaded = model["model_name"] in downloaded
            voices.append({
                "id": model["id"],
                "name": model["name"],
                "model_name": model["model_name"],
                "language": model["language"],
                "speaker_count": model["speaker_count"],
                "description": model["description"],
                "installed": is_downloaded,
                "path": None,
            })

        if not voices and self._is_tts_package_installed():
            voices.append({
                "id": "coqui_tts_default",
                "name": "Coqui TTS (Auto-download)",
                "model_name": "tts_models/en/ljspeech/tacotron2-DDC",
                "language": "en",
                "speaker_count": 1,
                "description": "Models auto-downloaded on first use via Coqui TTS.",
                "installed": True,
                "path": None,
            })

        return voices

    def _is_tts_package_installed(self) -> bool:
        """Check if the TTS Python package is installed."""
        try:
            import TTS
            return True
        except ImportError:
            return False

    def is_installed(self) -> bool:
        """Return True if TTS package is installed and models are available."""
        if not self._is_tts_package_installed():
            return False
        voices = self.detect_voices()
        return len(voices) > 0

    def get_voice_path(self, voice_id: str) -> Optional[Path]:
        """Return path to voice model files — DEPRECATED.

        Coqui TTS now uses model_name strings, not file paths.
        """
        voices = self.detect_voices()
        for v in voices:
            if v["id"] == voice_id:
                return Path(v["model_name"]) if v.get("installed") else None
        return None

    def get_voice_model_name(self, voice_id: str) -> Optional[str]:
        """Return the Coqui TTS model_name for a voice_id."""
        voices = self.detect_voices()
        for v in voices:
            if v["id"] == voice_id:
                return v.get("model_name")
        from tts_local.mirrors import get_default_model_name
        return get_default_model_name()

    def get_status(self) -> dict:
        """Return complete TTS installation status."""
        tts_installed = self._is_tts_package_installed()
        voices = self.detect_voices() if tts_installed else []

        return {
            "installed": tts_installed and len(voices) > 0,
            "tts_package_installed": tts_installed,
            "voices": voices,
            "models_dir": str(TTS_MODELS_DIR),
            "auto_download": True,
            "message": (
                "TTS models are auto-downloaded by Coqui TTS on first use. "
                "No manual download required."
            ) if tts_installed else (
                "TTS Python package not installed. Run: pip install TTS"
            ),
        }
