"""Reliable local TTS model download mirrors."""

from typing import List, Dict


def get_mirrors() -> List[Dict]:
    """Return prioritized mirrors for the default English voice model package."""
    return [
        {
            "url": "https://github.com/coqui-ai/TTS/releases/download/v0.22.0/tts_model_en_ljspeech_tacotron2.zip",
            "name": "Coqui LJSpeech Tacotron2 (Primary)",
            "voice_name": "default",
            "type": "zip",
        },
        {
            "url": "https://huggingface.co/coqui/XTTS-v2/resolve/main/model.zip",
            "name": "Coqui XTTS v2 (Fallback)",
            "voice_name": "default",
            "type": "zip",
        },
    ]