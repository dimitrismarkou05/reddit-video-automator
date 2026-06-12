"""Pydantic schemas for local TTS API."""

from typing import List, Optional
from pydantic import BaseModel


class VoiceInfo(BaseModel):
    id: str
    name: str
    model_name: str
    language: str
    speaker_count: int
    description: str
    installed: bool
    path: Optional[str] = None


class TtsStatusResponse(BaseModel):
    installed: bool
    tts_package_installed: bool
    voices: List[VoiceInfo]
    models_dir: str
    auto_download: bool
    message: str


class TtsInstallResponse(BaseModel):
    success: bool
    message: str
    model_name: str | None = None
    voice_path: str | None = None
    error: str | None = None
