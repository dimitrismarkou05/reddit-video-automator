import subprocess
from pathlib import Path
from typing import Optional, Callable

from core.config import FFMPEG_PATH, VIDEO_FORMATS
from video.engine.utils import (
    get_video_info,
    calculate_target_dimensions,
    select_background_video,
)


class FFmpegComposerError(Exception):
    pass


class FFmpegComposer:
    def __init__(self, ffmpeg_path: str = FFMPEG_PATH):
        self.ffmpeg_path = ffmpeg_path
        self._validate_ffmpeg()

    def _validate_ffmpeg(self):
        result = subprocess.run(
            [self.ffmpeg_path, "-version"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise FFmpegComposerError(f"FFmpeg not found at {self.ffmpeg_path}")

    def compose(
        self,
        background_video: str,
        audio_path: str,
        subtitle_path: Optional[str],
        output_path: str,
        video_format: str = "shorts",
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> float:
        target_w, target_h = calculate_target_dimensions(video_format)

        bg_duration, bg_w, bg_h = get_video_info(background_video)
        audio_duration, _, _ = get_video_info(audio_path)
        final_duration = audio_duration

        # Build filter complex for scaling + subtitle burn-in
        base_filter = (
            f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h}"
        )

        if subtitle_path and Path(subtitle_path).exists():
            # Escape path for FFmpeg filter
            sub_path_escaped = str(subtitle_path).replace("\\", "/").replace(":", "\\:")
            filter_complex = f"{base_filter},subtitles={sub_path_escaped}[v]"
        else:
            filter_complex = f"{base_filter}[v]"

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-stream_loop", "-1",
            "-i", background_video,
            "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-shortest",
            "-t", str(final_duration),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path,
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )

        for line in process.stdout:
            if progress_callback and "time=" in line:
                try:
                    time_str = line.split("time=")[1].split()[0]
                    h, m, s = time_str.split(":")
                    current_sec = float(h) * 3600 + float(m) * 60 + float(s)
                    percent = min(int((current_sec / final_duration) * 100), 99)
                    progress_callback(percent, "compositing")
                except (IndexError, ValueError):
                    pass

        process.wait()
        if process.returncode != 0:
            raise FFmpegComposerError(f"FFmpeg failed with code {process.returncode}")

        if progress_callback:
            progress_callback(100, "compositing complete")

        out_duration, _, _ = get_video_info(output_path)
        return out_duration

    def extract_thumbnail_frame(
        self,
        video_path: str,
        output_path: str,
        timestamp: float = 1.0,
    ) -> None:
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-ss", str(timestamp),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            raise FFmpegComposerError(f"Frame extraction failed: {result.stderr.decode()}")
