"""Async FFmpeg video composer with timeout and proper stream handling."""

import asyncio
import os
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
        self._current_process: Optional[asyncio.subprocess.Process] = None
        self._cancelled = False

    def _validate_ffmpeg(self):
        result = subprocess.run(
            [self.ffmpeg_path, "-version"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise FFmpegComposerError(f"FFmpeg not found at {self.ffmpeg_path}")

    def cancel(self) -> None:
        """Cancel the current FFmpeg operation."""
        self._cancelled = True
        if self._current_process:
            try:
                self._current_process.kill()
            except Exception:
                pass

    async def compose(
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

        base_filter = (
            f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h}"
        )

        if subtitle_path and Path(subtitle_path).exists():
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

        self._cancelled = False
        self._current_process = None

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self._current_process = process

            last_progress = 0
            while True:
                if self._cancelled:
                    process.kill()
                    raise FFmpegComposerError("FFmpeg composition was cancelled")

                line = await process.stdout.readline()
                if not line:
                    break

                line_str = line.decode("utf-8", errors="replace")

                if progress_callback and "time=" in line_str:
                    try:
                        time_str = line_str.split("time=")[1].split()[0]
                        h, m, s = time_str.split(":")
                        current_sec = float(h) * 3600 + float(m) * 60 + float(s)
                        percent = min(int((current_sec / final_duration) * 100), 99)
                        if percent > last_progress:
                            last_progress = percent
                            progress_callback(percent, "compositing")
                    except (IndexError, ValueError):
                        pass

            # Wait with timeout
            try:
                returncode = await asyncio.wait_for(process.wait(), timeout=3600)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise FFmpegComposerError("FFmpeg composition timed out after 1 hour")

            if returncode != 0:
                raise FFmpegComposerError(f"FFmpeg failed with code {returncode}")

            if progress_callback:
                progress_callback(100, "compositing complete")

            out_duration, _, _ = get_video_info(output_path)
            return out_duration

        finally:
            self._current_process = None

    async def extract_thumbnail_frame(
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
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
            except asyncio.TimeoutError:
                process.kill()
                raise FFmpegComposerError("Thumbnail frame extraction timed out")

            if process.returncode != 0:
                raise FFmpegComposerError(f"Frame extraction failed: {stderr.decode()}")
        except FFmpegComposerError:
            raise
        except Exception as exc:
            raise FFmpegComposerError(f"Frame extraction error: {exc}")
