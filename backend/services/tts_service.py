"""Core local TTS detection and management service."""

from typing import List, Dict, Optional

from sqlalchemy.orm import Session

from tts_local.detector import TtsDetector


class TTSService:
    """Service for local TTS operations."""

    def __init__(self, db: Session):
        self.db = db
        self.detector = TtsDetector()

    def get_status(self) -> dict:
        return self.detector.get_status()

    def list_voices(self) -> List[Dict]:
        return self.detector.detect_voices()

    def get_voice_model_name(self, voice_id: str) -> Optional[str]:
        return self.detector.get_voice_model_name(voice_id)

    def preload_default(self) -> None:
        """Preload the default TTS model to warm up cache."""
        try:
            from tts_local.mirrors import get_default_model_name
            from TTS.api import TTS
            TTS(model_name=get_default_model_name(), progress_bar=False, gpu=False)
        except Exception:
            pass
