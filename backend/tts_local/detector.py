"""Local TTS model detection logic using Coqui TTS API.

Models are auto-managed by Coqui TTS via pip. We return a static curated
list from mirrors.py. First-use download happens naturally in the engine.
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class TtsDetector:
    """Detects installed local TTS voice models via Coqui TTS API."""

    def detect_voices(self) -> List[Dict]:
        """Return static curated list from mirrors.py."""
        from tts_local.mirrors import get_available_models
        voices = []
        for model in get_available_models():
            voices.append({
                "id": model["id"],
                "name": model["name"],
                "model_name": model["model_name"],
                "language": model["language"],
                "speaker_count": model["speaker_count"],
                "description": model["description"],
                "installed": False,  # unknown until first use, but schema expects bool
                "path": None,
            })
        return voices

    def _is_tts_package_installed(self) -> bool:
        """Check if the TTS Python package is installed."""
        try:
            import TTS
            logger.info("[TtsDetector] TTS package imported successfully")
            return True
        except ImportError as e:
            logger.warning(f"[TtsDetector] TTS package not found: {e}")
            return False
        except Exception as e:
            logger.error(f"[TtsDetector] Unexpected error importing TTS: {type(e).__name__}: {e}")
            return False

    def is_installed(self) -> bool:
        """Return True if TTS package is importable."""
        return self._is_tts_package_installed()

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
            "installed": tts_installed,
            "tts_package_installed": tts_installed,
            "voices": voices,
            "models_dir": "",
            "auto_download": True,
            "message": (
                "TTS ready. Voice model downloads on first use (~500MB)."
            ) if tts_installed else (
                "TTS Python package not installed. Reinstall the application."
            ),
        }
