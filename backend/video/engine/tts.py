"""Local TTS orchestration using Coqui TTS."""

from pathlib import Path
from typing import Optional

from TTS.api import TTS
from sqlalchemy.orm import Session

from services.tts_service import TTSService
from video.engine.utils import get_audio_duration
import logging

logger = logging.getLogger(__name__)


class TTSProviderError(Exception):
    pass


class LocalTTSProvider:
    def __init__(self, voice_path: Path):
        self.voice_path = voice_path
        self.config_path = voice_path / "config.json"
        self.model_path = self._find_model_file(voice_path)
        self.tts: Optional[TTS] = None

    def _find_model_file(self, voice_path: Path) -> Path:
        for path in voice_path.iterdir():
            if path.is_file() and path.suffix in (".pth", ".onnx"):
                return path
        raise TTSProviderError(f"No model file (.pth or .onnx) found in {voice_path}")

    def _load(self) -> None:
        if self.tts is None:
            try:
                self.tts = TTS(
                    model_path=str(self.model_path),
                    config_path=str(self.config_path),
                    progress_bar=False,
                    gpu=False,
                )
            except Exception as exc:
                raise TTSProviderError(f"Failed to load TTS model: {exc}")

    def synthesize(self, text: str, output_path: Path) -> float:
        try:
            self._load()
            self.tts.tts_to_file(text=text, file_path=str(output_path))
            duration = get_audio_duration(str(output_path))
            return duration
        except Exception as exc:
            raise TTSProviderError(f"Local TTS synthesis failed: {exc}")


class TTSEngine:
    def __init__(self, db: Session):
        self.db = db
        self.service = TTSService(db)

    def get_provider(self, voice_id: str = "default") -> LocalTTSProvider:
        voice_path = self.service.get_voice_path(voice_id)
        if not voice_path:
            available = [v["id"] for v in self.service.list_voices()]
            raise TTSProviderError(
                f"Voice '{voice_id}' not found. Available: {available}. "
                f"Install a TTS model in Settings."
            )
        return LocalTTSProvider(voice_path)

    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
    ) -> float:
        tts = self.get_provider(voice_id)
        return tts.synthesize(text, output_path)

    def list_available_voices(self) -> list[dict]:
        return self.service.list_voices()