"""FFmpeg video composer using thread-pool for cross-platform compatibility."""

import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Callable

from core.config import FFMPEG_PATH
from video.engine.utils import (
    get_video_info,
    calculate_target_dimensions,
    get_audio_duration,
)


class FFmpegComposerError(Exception):
    pass


class FFmpegComposer:
    def __init__(self, ffmpeg_path: str = FFMPEG_PATH):
        self.ffmpeg_path = ffmpeg_path
        self._process: Optional[subprocess.Popen] = None
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
        if self._process:
            try:
                self._process.kill()
            except Exception:
                pass

    async def compose(
        self,
        background_video: str,
        audio_path: str,
        subtitle_path: Optional[str],
        output_path: str,
        video_format: str = "shorts",
        audio_duration: Optional[float] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> float:
        target_w, target_h = calculate_target_dimensions(video_format)

        # Get background info (not strictly needed but kept for consistency)
        get_video_info(background_video)

        # Determine final duration
        if audio_duration is None:
            audio_duration = get_audio_duration(audio_path)
        final_duration = audio_duration

        # Build base filter
        base_filter = (
            f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h}"
        )

        if subtitle_path and Path(subtitle_path).exists():
            # Convert Windows backslashes to forward slashes
            sub_path = str(subtitle_path).replace("\\", "/")
            # Escape colon after drive letter (e.g., C:/ -> C\:/)
            if ':' in sub_path:
                # Replace first colon with \:
                sub_path = sub_path.replace(':', '\\:', 1)
            # Use filename= option and wrap in single quotes for safety
            filter_complex = f"{base_filter},subtitles=filename='{sub_path}'[v]"
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
            "-preset", "ultrafast",
            "-crf", "283",
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
        self._process = None

        # Synchronous runner that reads stdout and stderr separately
        def run_ffmpeg():
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            last_progress = 0
            # Read stdout line by line for progress
            for line in iter(self._process.stdout.readline, ""):
                if self._cancelled:
                    self._process.kill()
                    self._process.wait()
                    raise FFmpegComposerError("FFmpeg composition was cancelled")

                if progress_callback and "time=" in line:
                    try:
                        time_str = line.split("time=")[1].split()[0]
                        h, m, s = time_str.split(":")
                        current_sec = float(h) * 3600 + float(m) * 60 + float(s)
                        percent = min(int((current_sec / final_duration) * 100), 99)
                        if percent > last_progress:
                            last_progress = percent
                            progress_callback(percent, "compositing")
                    except (IndexError, ValueError):
                        pass

            # Wait for process and capture stderr
            returncode = self._process.wait()
            stderr = self._process.stderr.read()
            return returncode, stderr

        # Run in thread
        try:
            returncode, stderr = await asyncio.to_thread(run_ffmpeg)
            if returncode != 0:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"FFmpeg stderr:\n{stderr}")
                raise FFmpegComposerError(f"FFmpeg failed with code {returncode}. See logs for details.")

            if progress_callback:
                progress_callback(100, "compositing complete")

            out_duration, _, _ = get_video_info(output_path)
            return out_duration

        except Exception as exc:
            raise FFmpegComposerError(f"FFmpeg composition error: {exc}")
        finally:
            self._process = None

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

        def run_thumbnail():
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise FFmpegComposerError(f"Frame extraction failed: {result.stderr}")

        try:
            await asyncio.to_thread(run_thumbnail)
        except subprocess.TimeoutExpired:
            raise FFmpegComposerError("Thumbnail frame extraction timed out")
        except Exception as exc:
            raise FFmpegComposerError(f"Frame extraction error: {exc}")