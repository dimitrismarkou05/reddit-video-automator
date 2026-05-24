"""Pydantic schemas for local TTS API."""

from typing import List
from pydantic import BaseModel


class VoiceInfo(BaseModel):
    id: str
    name: str
    path: str


class TtsStatusResponse(BaseModel):
    installed: bool
    voices: List[VoiceInfo]
    models_dir: str


class TtsInstallResponse(BaseModel):
    success: bool
    message: str
    voice_path: str | None = None
    error: str | None = None