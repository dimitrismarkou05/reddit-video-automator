"""Shared text normalization helpers."""

import re


def normalize_for_tts(text: str) -> str:
    """Normalize Unicode punctuation for TTS engines with limited vocabularies."""
    if not text:
        return ""
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201C", '"').replace("\u201D", '"')
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    text = text.replace("\u2026", "...")
    text = re.sub(r"\.{4,}", "...", text)
    return text
