"""FFmpeg path storage and retrieval via SettingsManager."""

import json
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from core.settings_manager import SettingsManager


#    Quality Presets
# Each quality level maps to a recommended CRF + preset combo.
# Higher quality = slower encoding (more compression efficiency).
# render_factor is relative to balanced (~veryfast) for a typical 3-minute clip.
QUALITY_PRESETS = {
    "draft": {
        "preset": "ultrafast",
        "crf": "28",
        "label": "Draft (fastest)",
        "render_time_hint": "~2-3x faster than balanced. Best for testing.",
    },
    "fast": {
        "preset": "superfast",
        "crf": "26",
        "label": "Fast",
        "render_time_hint": "~1.5x faster than balanced. Good for drafts.",
    },
    "balanced": {
        "preset": "veryfast",
        "crf": "23",
        "label": "Balanced",
        "render_time_hint": "Recommended default. Good speed/quality balance.",
    },
    "quality": {
        "preset": "medium",
        "crf": "20",
        "label": "High Quality",
        "render_time_hint": "~2-3x slower than balanced. Better compression.",
    },
    "archival": {
        "preset": "slow",
        "crf": "18",
        "label": "Archival (slowest)",
        "render_time_hint": "~5-10x slower than balanced. Use for final exports only.",
    },
}

SLOW_PRESETS = frozenset({"slow", "slower", "veryslow"})

# Relative encode time vs balanced (veryfast). Used for timeout scaling and UI hints.
PRESET_RENDER_FACTORS: Dict[str, float] = {
    "ultrafast": 0.5,
    "superfast": 0.7,
    "veryfast": 1.0,
    "faster": 1.2,
    "fast": 1.5,
    "medium": 2.5,
    "slow": 5.0,
    "slower": 7.0,
    "veryslow": 10.0,
}

PRESET_RENDER_TIME_HINTS: Dict[str, str] = {
    "ultrafast": "~0.5x balanced encode time. Largest files.",
    "superfast": "~0.7x balanced encode time.",
    "veryfast": "Baseline speed (balanced default).",
    "faster": "~1.2x balanced encode time.",
    "fast": "~1.5x balanced encode time.",
    "medium": "~2.5x balanced encode time.",
    "slow": "~5x balanced encode time. Significantly longer compositing.",
    "slower": "~7x balanced encode time. Not recommended for routine use.",
    "veryslow": "~10x balanced encode time. May take many minutes per video.",
}


def get_preset_timeout_multiplier(preset: str) -> float:
    """Scale compose watchdog timeout by encoding preset slowness."""
    return max(PRESET_RENDER_FACTORS.get(preset, 1.0), 1.0)


def get_slow_preset_warning(preset: str, quality: str) -> Optional[str]:
    """Return a user-facing warning when encode settings are unusually slow."""
    if quality == "archival":
        return (
            "Archival quality uses the slow preset and can take 5-10x longer to "
            "composite than balanced. Consider balanced or fast for everyday videos."
        )
    if preset in SLOW_PRESETS:
        factor = PRESET_RENDER_FACTORS.get(preset, 5.0)
        return (
            f"Encoding preset '{preset}' is ~{factor:.0f}x slower than balanced. "
            "Compositing may take several minutes even for short videos."
        )
    return None

#    Video Codec Options                                            
VIDEO_CODECS = {
    "libx264":  "H.264 (libx264) — Best compatibility",
    "libx265":  "H.265 / HEVC (libx265) — Better compression",
    "libvpx-vp9": "VP9 (libvpx-vp9) — Web optimized",
}

#    Preset Options                                                 
PRESET_OPTIONS = [
    "ultrafast", "superfast", "veryfast", "faster", "fast",
    "medium", "slow", "slower", "veryslow",
]

#    Pixel Format Options                                           
PIXEL_FORMATS = {
    "yuv420p":   "yuv420p — Best compatibility",
    "yuv444p":   "yuv444p — Full chroma (larger files)",
    "yuv422p":   "yuv422p — Balanced chroma",
    "p010le":    "p010le — 10-bit (HDR support)",
}

#    Audio Codec Options                                            
AUDIO_CODECS = {
    "aac":       "AAC — Best compatibility",
    "libmp3lame": "MP3 — Wide support",
    "libopus":   "Opus — Best quality at low bitrates",
    "flac":      "FLAC — Lossless (large files)",
}

#    Audio Bitrate Options                                          
AUDIO_BITRATES = {
    "96k":   "96 kbps — Low (voice only)",
    "128k":  "128 kbps — Standard",
    "192k":  "192 kbps — Good quality",
    "256k":  "256 kbps — High quality",
    "320k":  "320 kbps — Maximum",
}

#    Audio Sample Rate Options                                      
AUDIO_SAMPLE_RATES = {
    "22050": "22050 Hz — Low",
    "44100": "44100 Hz — CD quality",
    "48000": "48000 Hz — Standard video",
    "96000": "96000 Hz — High-res audio",
}


class FFmpegSettings:
    """Manages FFmpeg/FFprobe path persistence and video generation settings."""

    # Binary path keys
    FFMPEG_PATH_KEY = "ffmpeg_path"
    FFPROBE_PATH_KEY = "ffprobe_path"
    FFMPEG_VERSION_KEY = "ffmpeg_version"
    FFPROBE_VERSION_KEY = "ffprobe_version"

    # Video generation setting keys
    VIDEO_QUALITY_KEY = "video_quality"
    VIDEO_CODEC_KEY = "video_codec"
    VIDEO_PRESET_KEY = "video_preset"
    VIDEO_CRF_KEY = "video_crf"
    VIDEO_BITRATE_KEY = "video_bitrate"
    PIXEL_FORMAT_KEY = "pixel_format"
    AUDIO_CODEC_KEY = "audio_codec"
    AUDIO_BITRATE_KEY = "audio_bitrate"
    AUDIO_SAMPLE_RATE_KEY = "audio_sample_rate"

    # Defaults
    DEFAULT_QUALITY = "balanced"
    DEFAULT_CODEC = "libx264"
    DEFAULT_PRESET = "veryfast"
    DEFAULT_CRF = "23"
    DEFAULT_BITRATE = ""        # empty = use CRF instead
    DEFAULT_PIXEL_FORMAT = "yuv420p"
    DEFAULT_AUDIO_CODEC = "aac"
    DEFAULT_AUDIO_BITRATE = "192k"
    DEFAULT_AUDIO_SAMPLE_RATE = "44100"

    def __init__(self, db: Session):
        self._mgr = SettingsManager(db)

    #    Binary paths                                                 

    def get_ffmpeg_path(self) -> Optional[str]:
        return self._mgr.get(self.FFMPEG_PATH_KEY)

    def set_ffmpeg_path(self, path: str) -> None:
        self._mgr.set(self.FFMPEG_PATH_KEY, path)

    def get_ffprobe_path(self) -> Optional[str]:
        return self._mgr.get(self.FFPROBE_PATH_KEY)

    def set_ffprobe_path(self, path: str) -> None:
        self._mgr.set(self.FFPROBE_PATH_KEY, path)

    def get_ffmpeg_version(self) -> Optional[str]:
        return self._mgr.get(self.FFMPEG_VERSION_KEY)

    def set_ffmpeg_version(self, version: str) -> None:
        self._mgr.set(self.FFMPEG_VERSION_KEY, version)

    def get_ffprobe_version(self) -> Optional[str]:
        return self._mgr.get(self.FFPROBE_VERSION_KEY)

    def set_ffprobe_version(self, version: str) -> None:
        self._mgr.set(self.FFPROBE_VERSION_KEY, version)

    def clear_all(self) -> None:
        """Remove all FFmpeg-related settings."""
        for key in (
            self.FFMPEG_PATH_KEY,
            self.FFPROBE_PATH_KEY,
            self.FFMPEG_VERSION_KEY,
            self.FFPROBE_VERSION_KEY,
        ):
            self._mgr.set(key, "")

    #    Video generation settings                                    

    def get_video_quality(self) -> str:
        return self._mgr.get(self.VIDEO_QUALITY_KEY, self.DEFAULT_QUALITY) or self.DEFAULT_QUALITY

    def set_video_quality(self, quality: str) -> None:
        self._mgr.set(self.VIDEO_QUALITY_KEY, quality)

    def get_video_codec(self) -> str:
        return self._mgr.get(self.VIDEO_CODEC_KEY, self.DEFAULT_CODEC) or self.DEFAULT_CODEC

    def set_video_codec(self, codec: str) -> None:
        self._mgr.set(self.VIDEO_CODEC_KEY, codec)

    def get_video_preset(self) -> str:
        return self._mgr.get(self.VIDEO_PRESET_KEY, self.DEFAULT_PRESET) or self.DEFAULT_PRESET

    def set_video_preset(self, preset: str) -> None:
        self._mgr.set(self.VIDEO_PRESET_KEY, preset)

    def get_video_crf(self) -> str:
        return self._mgr.get(self.VIDEO_CRF_KEY, self.DEFAULT_CRF) or self.DEFAULT_CRF

    def set_video_crf(self, crf: str) -> None:
        self._mgr.set(self.VIDEO_CRF_KEY, crf)

    def get_video_bitrate(self) -> str:
        return self._mgr.get(self.VIDEO_BITRATE_KEY, self.DEFAULT_BITRATE) or self.DEFAULT_BITRATE

    def set_video_bitrate(self, bitrate: str) -> None:
        self._mgr.set(self.VIDEO_BITRATE_KEY, bitrate)

    def get_pixel_format(self) -> str:
        return self._mgr.get(self.PIXEL_FORMAT_KEY, self.DEFAULT_PIXEL_FORMAT) or self.DEFAULT_PIXEL_FORMAT

    def set_pixel_format(self, fmt: str) -> None:
        self._mgr.set(self.PIXEL_FORMAT_KEY, fmt)

    def get_audio_codec(self) -> str:
        return self._mgr.get(self.AUDIO_CODEC_KEY, self.DEFAULT_AUDIO_CODEC) or self.DEFAULT_AUDIO_CODEC

    def set_audio_codec(self, codec: str) -> None:
        self._mgr.set(self.AUDIO_CODEC_KEY, codec)

    def get_audio_bitrate(self) -> str:
        return self._mgr.get(self.AUDIO_BITRATE_KEY, self.DEFAULT_AUDIO_BITRATE) or self.DEFAULT_AUDIO_BITRATE

    def set_audio_bitrate(self, bitrate: str) -> None:
        self._mgr.set(self.AUDIO_BITRATE_KEY, bitrate)

    def get_audio_sample_rate(self) -> str:
        return self._mgr.get(self.AUDIO_SAMPLE_RATE_KEY, self.DEFAULT_AUDIO_SAMPLE_RATE) or self.DEFAULT_AUDIO_SAMPLE_RATE

    def set_audio_sample_rate(self, rate: str) -> None:
        self._mgr.set(self.AUDIO_SAMPLE_RATE_KEY, rate)

    def get_all_video_settings(self) -> Dict[str, Any]:
        """Return a dict with all video generation settings for the frontend."""
        quality = self.get_video_quality()
        preset = self.get_video_preset()
        crf = self.get_video_crf()

        # If a quality preset is selected, apply its CRF/preset defaults
        # but allow overrides if the user has explicitly changed them.
        quality_data = QUALITY_PRESETS.get(quality, QUALITY_PRESETS[self.DEFAULT_QUALITY])

        slow_warning = get_slow_preset_warning(preset, quality)
        return {
            "quality": quality,
            "quality_label": quality_data["label"],
            "quality_render_time_hint": quality_data.get(
                "render_time_hint",
                QUALITY_PRESETS[self.DEFAULT_QUALITY]["render_time_hint"],
            ),
            "video_codec": self.get_video_codec(),
            "video_preset": preset,
            "video_crf": crf,
            "video_bitrate": self.get_video_bitrate(),
            "pixel_format": self.get_pixel_format(),
            "audio_codec": self.get_audio_codec(),
            "audio_bitrate": self.get_audio_bitrate(),
            "audio_sample_rate": self.get_audio_sample_rate(),
            "preset_render_time_hint": PRESET_RENDER_TIME_HINTS.get(
                preset, PRESET_RENDER_TIME_HINTS[self.DEFAULT_PRESET]
            ),
            "is_slow_encoding": bool(slow_warning),
            "slow_preset_warning": slow_warning,
        }

    def get_effective_encode_params(self) -> Dict[str, str]:
        """Return the effective FFmpeg encode parameters for the composer.

        Resolves quality presets into concrete CRF + preset values.
        If a video_bitrate is explicitly set, CRF is omitted in favour of -b:v.
        """
        quality = self.get_video_quality()
        quality_data = QUALITY_PRESETS.get(quality, QUALITY_PRESETS[self.DEFAULT_QUALITY])

        # User may have overridden preset/CRF individually
        preset = self.get_video_preset()
        crf = self.get_video_crf()

        # Fall back to quality preset values if the user hasn't explicitly changed
        if preset == self.DEFAULT_PRESET and quality_data["preset"] != self.DEFAULT_PRESET:
            preset = quality_data["preset"]

        # CRF: user override takes precedence; fall back to quality preset
        effective_crf = crf if crf != self.DEFAULT_CRF else quality_data["crf"]

        bitrate = self.get_video_bitrate()

        params: Dict[str, str] = {
            "video_codec": self.get_video_codec(),
            "preset": preset,
            "pixel_format": self.get_pixel_format(),
            "audio_codec": self.get_audio_codec(),
            "audio_bitrate": self.get_audio_bitrate(),
            "audio_sample_rate": self.get_audio_sample_rate(),
        }

        if bitrate:
            params["video_bitrate"] = bitrate
        else:
            params["crf"] = effective_crf

        return params

    def apply_quality_preset(self, quality: str) -> None:
        """Apply a quality preset, updating CRF and preset accordingly."""
        data = QUALITY_PRESETS.get(quality, QUALITY_PRESETS[self.DEFAULT_QUALITY])
        self.set_video_quality(quality)
        self.set_video_preset(data["preset"])
        self.set_video_crf(data["crf"])