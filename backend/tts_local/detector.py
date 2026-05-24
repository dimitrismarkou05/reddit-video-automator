"""Local TTS model detection logic."""

import json
from pathlib import Path
from typing import List, Dict, Optional

from core.config import TTS_MODELS_DIR


class TtsDetector:
    """Detects installed local TTS voice models."""

    def detect_voices(self) -> List[Dict]:
        voices: List[Dict] = []
        if not TTS_MODELS_DIR.exists():
            return voices
        for voice_dir in sorted(TTS_MODELS_DIR.iterdir()):
            if not voice_dir.is_dir():
                continue
            config_file = voice_dir / "config.json"
            model_file = self._find_model_file(voice_dir)
            if config_file.exists() and model_file is not None:
                voices.append(
                    {
                        "id": voice_dir.name,
                        "name": voice_dir.name.replace("_", " ").title(),
                        "path": str(voice_dir),
                    }
                )
        return voices

    def _find_model_file(self, voice_dir: Path) -> Optional[Path]:
        for path in voice_dir.iterdir():
            if path.is_file() and path.suffix in (".pth", ".onnx"):
                return path
        return None

    def is_installed(self) -> bool:
        return len(self.detect_voices()) > 0

    def get_voice_path(self, voice_id: str) -> Optional[Path]:
        voice_dir = TTS_MODELS_DIR / voice_id
        config = voice_dir / "config.json"
        model = self._find_model_file(voice_dir)
        if config.exists() and model is not None:
            return voice_dir
        return None

    def get_status(self) -> dict:
        voices = self.detect_voices()
        return {
            "installed": len(voices) > 0,
            "voices": voices,
            "models_dir": str(TTS_MODELS_DIR),
        }