"""TTS orchestration supporting OpenAI and ElevenLabs."""

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import openai
from elevenlabs import ElevenLabs
from sqlalchemy.orm import Session

from core.settings_manager import SettingsManager
from video.engine.utils import get_audio_duration
import logging

logger = logging.getLogger(__name__)


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

            duration = get_audio_duration(str(output_path))
            return duration
        except openai.AuthenticationError as exc:
            raise TTSProviderError(f"OpenAI API key rejected: {exc}")
        except openai.RateLimitError as exc:
            raise TTSProviderError(f"OpenAI rate limit exceeded: {exc}")
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
        self.client = ElevenLabs(api_key=api_key)

    def synthesize(self, text: str, voice: str, output_path: Path) -> float:
        try:
            audio_generator = self.client.text_to_speech.convert(
                voice_id=voice,
                output_format="mp3_44100_128",
                text=text,
                model_id="eleven_monolingual_v1",
            )

            audio_bytes = b"".join(audio_generator)
            output_path.write_bytes(audio_bytes)

            duration = get_audio_duration(str(output_path))
            return duration
        except Exception as exc:
            if "api key" in str(exc).lower() or "unauthorized" in str(exc).lower():
                raise TTSProviderError(f"ElevenLabs API key rejected: {exc}")
            raise TTSProviderError(f"ElevenLabs TTS failed: {exc}")

    def list_voices(self) -> list[dict]:
        try:
            response = self.client.voices.get_all()
            return [
                {
                    "id": v.voice_id,
                    "name": v.name,
                    "description": v.labels.get("description", "") if v.labels else "",
                }
                for v in response.voices
            ]
        except Exception as exc:
            raise TTSProviderError(f"Failed to list ElevenLabs voices: {exc}")


class TTSEngine:
    PROVIDERS = {
        "openai": OpenAITTSProvider,
        "elevenlabs": ElevenLabsTTSProvider,
    }

    FALLBACK_VOICES = {
        "openai": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
        "elevenlabs": [],
    }

    def __init__(self, db: Session):
        self.db = db
        self.settings = SettingsManager(db)

    def get_provider(self, provider_name: str, voice: Optional[str] = None) -> BaseTTSProvider:
        provider_class = self.PROVIDERS.get(provider_name)
        if not provider_class:
            raise TTSProviderError(f"Unknown TTS provider: {provider_name}")

        key_map = {
            "openai": "openai_api_key",
            "elevenlabs": "elevenlabs_api_key",
        }
        setting_key = key_map[provider_name]
        
        api_key = self.settings.get(setting_key, decrypt_value=True)
        
        if not api_key:
            # Check if there's a raw encrypted value that failed decryption
            raw = self.settings.get(setting_key, decrypt_value=False)
            if raw:
                logger.error(f"[TTSEngine] API key for '{setting_key}' exists but decryption returned None. Key file may have changed.")
                raise TTSProviderError(
                    f"{provider_name} API key is corrupted (encryption key mismatch). "
                    f"Re-save it in Settings → API Keys."
                )
            raise TTSProviderError(
                f"{provider_name} API key not configured. Set it in Settings → API Keys."
            )

        return provider_class(api_key)

    def get_fallback_voice(self, provider: str, failed_voice: str) -> Optional[str]:
        """Get next available fallback voice for the provider."""
        voices = self.FALLBACK_VOICES.get(provider, [])
        if failed_voice in voices:
            idx = voices.index(failed_voice)
            if idx + 1 < len(voices):
                return voices[idx + 1]
        return None

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