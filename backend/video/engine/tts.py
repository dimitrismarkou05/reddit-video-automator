from pathlib import Path
from typing import Optional, Callable

from sqlalchemy.orm import Session

from services.tts_service import TTSService
from video.engine.utils import get_audio_duration
import logging

logger = logging.getLogger(__name__)


class TTSProviderError(Exception):
    pass


class LocalTTSProvider:
    """Coqui TTS provider using model_name auto-download."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.tts = None

    def _load(self, progress_callback: Optional[Callable[[int, str], None]] = None) -> None:
        if self.tts is None:
            try:
                if progress_callback:
                    progress_callback(0, "downloading_model")
                from TTS.api import TTS
                self.tts = TTS(
                    model_name=self.model_name,
                    progress_bar=False,
                    gpu=False,
                )
                if progress_callback:
                    progress_callback(100, "downloading_model")
            except Exception as exc:
                raise TTSProviderError(f"Failed to load TTS model '{self.model_name}': {exc}")

    def synthesize(self, text: str, output_path: Path, progress_callback: Optional[Callable[[int, str], None]] = None) -> float:
        try:
            self._load(progress_callback)
            
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Synthesize to file
            self.tts.tts_to_file(text=text, file_path=str(output_path))
            
            # Verify file was created
            if not output_path.exists():
                raise TTSProviderError(f"TTS output file was not created: {output_path}")
            
            if output_path.stat().st_size == 0:
                raise TTSProviderError(f"TTS output file is empty: {output_path}")
            
            # Get duration
            try:
                duration = get_audio_duration(str(output_path))
                return duration
            except Exception as duration_err:
                logger.error(f"Failed to get audio duration for {output_path}: {duration_err}")
                # Fallback: estimate duration based on text length
                # Average speaking rate is ~150 words per minute, ~2.5 words per second
                words = len(text.split())
                estimated_duration = words / 2.5
                logger.warning(f"Using estimated duration: {estimated_duration:.1f}s for {words} words")
                return estimated_duration
                
        except Exception as exc:
            raise TTSProviderError(f"Local TTS synthesis failed: {exc}")


class TTSEngine:
    def __init__(self, db: Session):
        self.db = db
        self.service = TTSService(db)

    def get_provider(self, voice_id: str = "default") -> LocalTTSProvider:
        model_name = self.service.get_voice_model_name(voice_id)
        if not model_name:
            from tts_local.mirrors import get_default_model_name
            model_name = get_default_model_name()
        return LocalTTSProvider(model_name)

    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> float:
        tts = self.get_provider(voice_id)
        return tts.synthesize(text, output_path, progress_callback=progress_callback)

    def list_available_voices(self) -> list[dict]:
        return self.service.list_voices()