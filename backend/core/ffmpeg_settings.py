"""FFmpeg path storage and retrieval via SettingsManager."""

import json
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from core.settings_manager import SettingsManager


#    Quality Presets                                                
# Each quality level maps to a recommended CRF + preset combo.
# Higher quality = slower encoding (more compression efficiency).
QUALITY_PRESETS = {
    "draft":      {"preset": "ultrafast", "crf": "28", "label": "Draft (fastest)"},
    "fast":       {"preset": "superfast", "crf": "26", "label": "Fast"},
    "balanced":   {"preset": "veryfast",  "crf": "23", "label": "Balanced"},
    "quality":    {"preset": "medium",    "crf": "20", "label": "High Quality"},
    "archival":   {"preset": "slow",      "crf": "18", "label": "Archival (slowest)"},
}

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

        return {
            "quality": quality,
            "quality_label": quality_data["label"],
            "video_codec": self.get_video_codec(),
            "video_preset": preset,
            "video_crf": crf,
            "video_bitrate": self.get_video_bitrate(),
            "pixel_format": self.get_pixel_format(),
            "audio_codec": self.get_audio_codec(),
            "audio_bitrate": self.get_audio_bitrate(),
            "audio_sample_rate": self.get_audio_sample_rate(),
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