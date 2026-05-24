"""Reliable local TTS model download mirrors.

NOTE: Coqui TTS models are now downloaded automatically via pip install TTS
and loaded by model_name (e.g. "tts_models/en/ljspeech/tacotron2-DDC").
The old zip download approach is deprecated and mirrors are broken.

This module now provides model metadata for the TTS engine to use
TTS().list_models() and TTS(model_name=...) auto-download.
"""

from typing import List, Dict


def get_mirrors() -> List[Dict]:
    """Return prioritized mirrors — DEPRECATED.

    Coqui TTS now auto-downloads models via pip. No manual zip needed.
    """
    return []


def get_default_model_name() -> str:
    """Return the default English TTS model name for Coqui TTS."""
    return "tts_models/en/ljspeech/tacotron2-DDC"


def get_available_models() -> List[Dict]:
    """Return a curated list of recommended Coqui TTS models."""
    return [
        {
            "id": "en_ljspeech_tacotron2_ddc",
            "name": "English (LJSpeech) – Tacotron2 DDC",
            "model_name": "tts_models/en/ljspeech/tacotron2-DDC",
            "language": "en",
            "speaker_count": 1,
            "description": "High-quality English female voice. Default recommendation.",
        },
        {
            "id": "en_ljspeech_vits",
            "name": "English (LJSpeech) – VITS",
            "model_name": "tts_models/en/ljspeech/vits",
            "language": "en",
            "speaker_count": 1,
            "description": "End-to-end VITS model, fast inference.",
        },
        {
            "id": "en_vctk_vits",
            "name": "English (VCTK) – VITS Multi-speaker",
            "model_name": "tts_models/en/vctk/vits",
            "language": "en",
            "speaker_count": 109,
            "description": "Multi-speaker English model with 109 speakers.",
        },
        {
            "id": "multilingual_xtts_v2",
            "name": "XTTS v2 – Multilingual Voice Cloning",
            "model_name": "tts_models/multilingual/multi-dataset/xtts_v2",
            "language": "multilingual",
            "speaker_count": 0,
            "description": "Clone any voice from 3s of audio. 17 languages.",
        },
    ]
