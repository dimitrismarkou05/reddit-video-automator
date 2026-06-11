"""Subtitle generation using faster-whisper transcription.

Changes from the original:
- Uses faster-whisper (4-8x faster, lower memory than openai-whisper).
- Real transcription progress via segment generator.
- 3-word-max segments (configurable), with pause/punctuation splits.
- End-times clamped to next segment start (no overlap, no future text on screen).
"""

import functools
import logging
from pathlib import Path
from typing import List, Optional, Callable

from video.schemas import SubtitleStyle

logger = logging.getLogger(__name__)

# Max words to show at once.  Configurable at call time.
DEFAULT_MAX_WORDS = 3
# Minimum pause between words that forces a new subtitle line (seconds).
PAUSE_SPLIT_THRESHOLD = 0.4
# Sentence-ending punctuation that triggers a subtitle split.
_SENTENCE_ENDS = frozenset(".!?")


@functools.lru_cache(maxsize=4)
def _load_whisper_model(model_size: str = "base"):
    """Load and cache a faster-whisper model. Pre-loaded at startup."""
    from faster_whisper import WhisperModel  # type: ignore[import-untyped]
    logger.info(f"[Whisper] Loading model: {model_size}")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    logger.info(f"[Whisper] Model loaded: {model_size}")
    return model


class SubtitleGenerator:
    def __init__(self, model_size: str = "base"):
        self.model = _load_whisper_model(model_size)
        self.model_size = model_size

    def transcribe(
        self,
        audio_path: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        audio_duration: Optional[float] = None,
    ) -> dict:
        """Transcribe *audio_path* and return a Whisper-compatible dict.

        If *progress_callback* is provided and *audio_duration* is known,
        real progress (0-100) is reported as segments are decoded.
        """
        logger.info(f"[Whisper] Transcribing: {audio_path}")
        seg_gen, info = self.model.transcribe(
            audio_path,
            word_timestamps=True,
            language="en",
        )

        total_dur = audio_duration or (info.duration if info.duration else 0)
        segments_out: list = []

        for seg in seg_gen:
            words = []
            for w in seg.words or []:
                words.append(
                    {"word": w.word, "start": w.start, "end": w.end}
                )
            segments_out.append(
                {
                    "id": len(segments_out),
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                    "words": words,
                }
            )

            if progress_callback and total_dur > 0:
                pct = min(int((seg.end / total_dur) * 100), 99)
                progress_callback(pct, "transcribing")

        if progress_callback:
            progress_callback(100, "transcribing")

        logger.info(
            f"[Whisper] Done: {len(segments_out)} segments "
            f"({info.duration:.1f}s detected)"
        )
        return {"segments": segments_out, "duration": info.duration}

    def generate_ass(
        self,
        whisper_result: dict,
        output_path: Path,
        style: SubtitleStyle,
        video_width: int = 1080,
        video_height: int = 1920,
        max_words: int = DEFAULT_MAX_WORDS,
    ) -> Path:
        """Write an ASS subtitle file with tight 2-4 word segments."""
        play_res_x = video_width
        play_res_y = video_height

        if style.position == "bottom":
            margin_v = int(video_height * 0.08)
        elif style.position == "top":
            margin_v = int(video_height * 0.85)
        else:  # center
            margin_v = int(video_height * 0.45)

        header = (
            f"[Script Info]\n"
            f"Title: Auto-generated subtitles\n"
            f"ScriptType: v4.00+\n"
            f"PlayResX: {play_res_x}\n"
            f"PlayResY: {play_res_y}\n\n"
            f"[V4+ Styles]\n"
            f"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            f"OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            f"ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            f"Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,Arial,{style.font_size},"
            f"&H00{style.font_color.lstrip('#')},"
            f"&H000000FF,"
            f"&H00{style.outline_color.lstrip('#')},"
            f"&H00000000,"
            f"0,0,0,0,100,100,0,0,1,{style.outline_width},0,"
            f"2,10,10,{margin_v},1\n\n"
            f"[Events]\n"
            f"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        # Collect all word objects.
        all_words: List[dict] = []
        for segment in whisper_result.get("segments", []):
            for word in segment.get("words", []):
                if word.get("word", "").strip():
                    all_words.append(word)

        if not all_words:
            output_path.write_text(header, encoding="utf-8")
            return output_path

        # Group words into display chunks (max_words, pause split, punctuation split).
        chunks: List[List[dict]] = []
        current: List[dict] = []

        for i, word in enumerate(all_words):
            should_flush = False

            if len(current) >= max_words:
                should_flush = True
            elif current:
                prev_end = current[-1]["end"]
                gap = word["start"] - prev_end
                if gap > PAUSE_SPLIT_THRESHOLD:
                    should_flush = True
                elif current[-1]["word"].strip().rstrip() and \
                        current[-1]["word"].strip()[-1] in _SENTENCE_ENDS:
                    should_flush = True

            if should_flush and current:
                chunks.append(current)
                current = []

            current.append(word)

        if current:
            chunks.append(current)

        # Build dialogue events with end-time clamping.
        dialogue_lines: List[str] = []
        for i, chunk in enumerate(chunks):
            text = " ".join(w["word"].strip() for w in chunk).strip()
            if not text:
                continue

            start_t = chunk[0]["start"]
            end_t = chunk[-1]["end"]

            # Clamp: must not overlap with the next chunk.
            if i + 1 < len(chunks):
                next_start = chunks[i + 1][0]["start"]
                if end_t > next_start:
                    end_t = max(start_t + 0.05, next_start - 0.001)

            # Minimum display time: 0.3 s.
            if end_t - start_t < 0.3:
                end_t = start_t + 0.3

            text = text.replace("{", "\\{").replace("}", "\\}")
            start_str = _format_time(start_t)
            end_str = _format_time(end_t)
            dialogue_lines.append(
                f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text}"
            )

        ass_content = header + "\n".join(dialogue_lines)
        output_path.write_text(ass_content, encoding="utf-8")
        logger.info(
            f"[Subtitles] Wrote {len(dialogue_lines)} events → {output_path.name}"
        )
        return output_path


def unload_whisper_models() -> None:
    """Release cached faster-whisper models to free RAM."""
    _load_whisper_model.cache_clear()
    logger.info("[Whisper] Model cache cleared")


def _parse_ass_time(value: str) -> float:
    """Parse ASS timestamp H:MM:SS.cc to seconds."""
    parts = value.strip().split(":")
    if len(parts) != 3:
        return 0.0
    hours = int(parts[0])
    minutes = int(parts[1])
    sec_parts = parts[2].split(".")
    secs = int(sec_parts[0])
    centis = int(sec_parts[1]) if len(sec_parts) > 1 else 0
    return hours * 3600 + minutes * 60 + secs + centis / 100.0


def slice_ass(
    ass_path: Path,
    output_path: Path,
    start_sec: float,
    end_sec: float,
) -> Path:
    """Write ASS dialogue events for [start_sec, end_sec) with times shifted to zero."""
    content = ass_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    header_lines: List[str] = []
    dialogue_lines: List[str] = []
    in_events = False
    past_format = False

    for line in lines:
        if line.startswith("[Events]"):
            in_events = True
            header_lines.append(line)
            continue
        if not in_events:
            header_lines.append(line)
            continue
        if line.startswith("Format:"):
            header_lines.append(line)
            past_format = True
            continue
        if not past_format or not line.startswith("Dialogue:"):
            continue

        # Dialogue: Layer, Start, End, Style, ...
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        ev_start = _parse_ass_time(parts[1])
        ev_end = _parse_ass_time(parts[2])
        if ev_end <= start_sec or ev_start >= end_sec:
            continue

        rel_start = max(0.0, ev_start - start_sec)
        rel_end = min(end_sec - start_sec, ev_end - start_sec)
        if rel_end <= rel_start:
            continue

        parts[1] = _format_time(rel_start)
        parts[2] = _format_time(rel_end)
        dialogue_lines.append(",".join(parts))

    output_path.write_text(
        "\n".join(header_lines + dialogue_lines) + "\n",
        encoding="utf-8",
    )
    return output_path


def _format_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int((seconds % 1) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"
