"""Core local TTS detection, installation, and management service."""

import asyncio
from pathlib import Path
from typing import List, Dict, Optional

from sqlalchemy.orm import Session

from core.config import TTS_MODELS_DIR
from tts_local.detector import TtsDetector
from tts_local.installer import TtsModelInstaller, cancel_active_install


class TTSService:
    """Service for local TTS operations."""

    def __init__(self, db: Session):
        self.db = db
        self.detector = TtsDetector()

    def get_status(self) -> dict:
        return self.detector.get_status()

    def list_voices(self) -> List[Dict]:
        return self.detector.detect_voices()

    def get_voice_path(self, voice_id: str) -> Optional[Path]:
        return self.detector.get_voice_path(voice_id)

    def install_sync(self) -> dict:
        installer = TtsModelInstaller()
        return installer.install()

    async def install(self) -> dict:
        return await asyncio.to_thread(self.install_sync)

    def cancel_install(self) -> None:
        cancel_active_install()

    def preload_default(self) -> None:
        voices = self.list_voices()
        if voices:
            from video.engine.tts import LocalTTSProvider

            provider = LocalTTSProvider(Path(voices[0]["path"]))
            provider._load()