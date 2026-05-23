"""Subtitle generation with Whisper transcription and ASS formatting."""

import functools
import re
from pathlib import Path
from typing import List, Tuple, Optional

import whisper

from video.schemas import SubtitleStyle


# Singleton pattern: module-level cached model
@functools.lru_cache(maxsize=2)
def _load_whisper_model(model_size: str = "base"):
    """Load and cache Whisper model. Pre-load on startup if possible."""
    return whisper.load_model(model_size)


class SubtitleGenerator:
    def __init__(self, model_size: str = "base"):
        self.model = _load_whisper_model(model_size)
        self.model_size = model_size

    def transcribe(self, audio_path: str) -> dict:
        """Transcribe audio and return Whisper result with word timestamps."""
        result = self.model.transcribe(
            audio_path,
            word_timestamps=True,
            language="en",
        )
        return result

    def generate_ass(
        self,
        whisper_result: dict,
        output_path: Path,
        style: SubtitleStyle,
        video_width: int = 1080,
        video_height: int = 1920,
    ) -> Path:
        play_res_x = video_width
        play_res_y = video_height

        margin_v = int(video_height * 0.15) if style.position == "bottom" else \
                   int(video_height * 0.15) if style.position == "top" else \
                   int(video_height * 0.45)

        max_width = int(video_width * (style.max_width_percent / 100))

        header = f"""[Script Info]
Title: Auto-generated subtitles
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{style.font_size},&H00{style.font_color.lstrip('#')},&H000000FF,&H00{style.outline_color.lstrip('#')},&H00000000,0,0,0,0,100,100,0,0,1,{style.outline_width},0,2,10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        lines = []
        current_line = []
        current_start = None
        current_end = None

        def flush_line(line_parts, start_time, end_time):
            if not line_parts:
                return [], None, None

            text = " ".join(line_parts)
            text = self._word_wrap(text, max_width, style.font_size)

            start = self._format_time(start_time)
            end = self._format_time(end_time)

            text = text.replace("{", "\\{").replace("}", "\\}")

            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
            return [], None, None

        for segment in whisper_result.get("segments", []):
            for word in segment.get("words", []):
                word_text = word["word"].strip()
                if not word_text:
                    continue

                word_start = word["start"]
                word_end = word["end"]

                if current_start is None:
                    current_start = word_start
                    current_end = word_end

                test_line = " ".join(current_line + [word_text])
                if self._estimate_text_width(test_line, style.font_size) > max_width and current_line:
                    current_line, current_start, current_end = flush_line(current_line, current_start, current_end)
                    current_start = word_start

                current_line.append(word_text)
                current_end = word_end

        flush_line(current_line, current_start, current_end)

        ass_content = header + "\n".join(lines)
        output_path.write_text(ass_content, encoding="utf-8")
        return output_path

    def _format_time(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centis = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"

    def _estimate_text_width(self, text: str, font_size: int) -> int:
        return int(len(text) * font_size * 0.6)

    def _word_wrap(self, text: str, max_width: int, font_size: int) -> str:
        words = text.split()
        lines = []
        current = []

        for word in words:
            test = " ".join(current + [word])
            if self._estimate_text_width(test, font_size) > max_width and current:
                lines.append(" ".join(current))
                current = [word]
            else:
                current.append(word)

        if current:
            lines.append(" ".join(current))

        return "\\N".join(lines)
