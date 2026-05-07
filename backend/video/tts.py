"""TTS orchestration supporting OpenAI and ElevenLabs."""

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import openai
from elevenlabs import generate, save, voices
from sqlalchemy.orm import Session

from backend.settings_manager import SettingsManager


class TTSProviderError(Exception):
    pass


class BaseTTSProvider(ABC):
    def __init__(self, api_key: str):
        self.api_key = api_key

    @abstractmethod
    def synthesize(self, text: str, voice: str, output_path: Path) -> float:
        """Synthesize text to speech. Returns: duration in seconds."""
        pass

    @abstractmethod
    def list_voices(self) -> list[dict]:
        pass


class OpenAITTSProvider(BaseTTSProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.client = openai.OpenAI(api_key=api_key)

    def synthesize(self, text: str, voice: str, output_path: Path) -> float:
        try:
            response = self.client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text,
            )
            response.stream_to_file(str(output_path))

            from backend.video.utils import get_video_info
            duration, _, _ = get_video_info(str(output_path))
            return duration
        except Exception as exc:
            raise TTSProviderError(f"OpenAI TTS failed: {exc}")

    def list_voices(self) -> list[dict]:
        return [
            {"id": "alloy", "name": "Alloy", "description": "Balanced, neutral"},
            {"id": "echo", "name": "Echo", "description": "Male, warm"},
            {"id": "fable", "name": "Fable", "description": "Male, British"},
            {"id": "onyx", "name": "Onyx", "description": "Male, deep"},
            {"id": "nova", "name": "Nova", "description": "Female, warm"},
            {"id": "shimmer", "name": "Shimmer", "description": "Female, clear"},
        ]


class ElevenLabsTTSProvider(BaseTTSProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        os.environ["ELEVEN_API_KEY"] = api_key

    def synthesize(self, text: str, voice: str, output_path: Path) -> float:
        try:
            audio = generate(
                text=text,
                voice=voice,
                model="eleven_monolingual_v1",
            )
            save(audio, str(output_path))

            from backend.video.utils import get_video_info
            duration, _, _ = get_video_info(str(output_path))
            return duration
        except Exception as exc:
            raise TTSProviderError(f"ElevenLabs TTS failed: {exc}")

    def list_voices(self) -> list[dict]:
        try:
            voice_list = voices()
            return [
                {"id": v.voice_id, "name": v.name, "description": v.category}
                for v in voice_list
            ]
        except Exception as exc:
            raise TTSProviderError(f"Failed to list ElevenLabs voices: {exc}")


class TTSEngine:
    PROVIDERS = {
        "openai": OpenAITTSProvider,
        "elevenlabs": ElevenLabsTTSProvider,
    }

    def __init__(self, db: Session):
        self.db = db
        self.settings = SettingsManager(db)

    def get_provider(self, provider_name: str) -> BaseTTSProvider:
        provider_class = self.PROVIDERS.get(provider_name)
        if not provider_class:
            raise TTSProviderError(f"Unknown TTS provider: {provider_name}")

        key_map = {
            "openai": "openai_api_key",
            "elevenlabs": "elevenlabs_api_key",
        }
        api_key = self.settings.get(key_map[provider_name], decrypt_value=True)
        if not api_key:
            raise TTSProviderError(
                f"{provider_name} API key not configured. Set it in Settings."
            )

        return provider_class(api_key)

    def synthesize(
        self,
        text: str,
        provider: str,
        voice: str,
        output_path: Path,
    ) -> float:
        tts = self.get_provider(provider)
        return tts.synthesize(text, voice, output_path)

    def list_available_voices(self, provider: str) -> list[dict]:
        tts = self.get_provider(provider)
        return tts.list_voices()
