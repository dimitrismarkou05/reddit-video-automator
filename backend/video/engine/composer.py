"""FFmpeg video composer using thread-pool for cross-platform compatibility."""

import asyncio
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Callable, Dict, Any

from core.config import FFMPEG_PATH
from core.ffmpeg_settings import get_preset_timeout_multiplier
from video.engine.utils import (
    get_video_info,
    calculate_target_dimensions,
    get_audio_duration,
)


class FFmpegComposerError(Exception):
    pass


# FFmpeg progress lines use carriage returns; match the latest time= stamp in a chunk.
_FFMPEG_TIME_RE = re.compile(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})")
_PROGRESS_THROTTLE_SEC = 2.0


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
        encode_params: Optional[Dict[str, Any]] = None,
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

        # Resolve encode parameters with sensible defaults
        params = self._resolve_encode_params(encode_params)

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-stream_loop", "-1",
            "-i", background_video,
            "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", params["video_codec"],
            "-preset", params["preset"],
        ]

        # Use CRF if no explicit bitrate is set
        if params.get("crf"):
            cmd.extend(["-crf", str(params["crf"])])
        elif params.get("video_bitrate"):
            cmd.extend(["-b:v", str(params["video_bitrate"])])
        else:
            # Fallback CRF
            cmd.extend(["-crf", "23"])

        cmd.extend([
            "-c:a", params["audio_codec"],
            "-b:a", params["audio_bitrate"],
            "-ar", params["audio_sample_rate"],
            "-shortest",
            "-t", str(final_duration),
            "-pix_fmt", params["pixel_format"],
            "-movflags", "+faststart",
        ])

        cmd.append(output_path)

        self._cancelled = False
        self._process = None

        # FFmpeg logs progress to stderr; drain it while running to avoid pipe deadlock.
        preset = params.get("preset", "veryfast")
        timeout_multiplier = get_preset_timeout_multiplier(preset)
        compose_timeout = max(
            600,
            int(final_duration * 20 * timeout_multiplier) + 120,
        )

        def _parse_time_percent(chunk: str) -> Optional[int]:
            if final_duration <= 0:
                return None
            matches = _FFMPEG_TIME_RE.findall(chunk)
            if not matches:
                return None
            time_str = matches[-1]
            try:
                h, m, s = time_str.split(":")
                current_sec = float(h) * 3600 + float(m) * 60 + float(s)
                return min(int((current_sec / final_duration) * 100), 99)
            except (ValueError, ZeroDivisionError):
                return None

        def run_ffmpeg():
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            stderr_lines: list[str] = []
            last_progress = 0
            last_callback_time = 0.0
            progress_lock = threading.Lock()
            stderr_tail = ""

            def report_progress(percent: int, force: bool = False) -> None:
                nonlocal last_progress, last_callback_time
                if not progress_callback:
                    return
                now = time.monotonic()
                with progress_lock:
                    if not force:
                        if percent <= last_progress:
                            return
                        if (
                            percent - last_progress < 1
                            and now - last_callback_time < _PROGRESS_THROTTLE_SEC
                        ):
                            return
                    last_progress = max(last_progress, percent)
                    last_callback_time = now
                    progress_callback(percent, "compositing")

            def drain_stderr() -> None:
                nonlocal stderr_tail
                while True:
                    chunk = self._process.stderr.read(512)
                    if chunk == "":
                        break
                    stderr_lines.append(chunk)
                    if self._cancelled:
                        return
                    stderr_tail = (stderr_tail + chunk)[-8192:]
                    percent = _parse_time_percent(stderr_tail)
                    if percent is not None:
                        report_progress(percent)

            stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
            stderr_thread.start()

            try:
                returncode = self._process.wait(timeout=compose_timeout)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
                raise FFmpegComposerError(
                    f"FFmpeg composition timed out after {compose_timeout} seconds"
                )
            finally:
                stderr_thread.join(timeout=10)

            if self._cancelled:
                raise FFmpegComposerError("FFmpeg composition was cancelled")

            if returncode == 0:
                report_progress(100, force=True)

            stderr = "".join(stderr_lines)
            return returncode, stderr

        # Run in thread
        try:
            returncode, stderr = await asyncio.to_thread(run_ffmpeg)
            if returncode != 0:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"FFmpeg stderr:\n{stderr}")
                raise FFmpegComposerError(f"FFmpeg failed with code {returncode}. See logs for details.")

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

    def _resolve_encode_params(self, encode_params: Optional[Dict[str, Any]]) -> Dict[str, str]:
        """Merge user-provided encode params with sensible defaults."""
        defaults = {
            "video_codec": "libx264",
            "preset": "veryfast",
            "crf": "23",
            "video_bitrate": "",
            "pixel_format": "yuv420p",
            "audio_codec": "aac",
            "audio_bitrate": "192k",
            "audio_sample_rate": "44100",
        }
        if encode_params:
            # Only update keys that have a non-empty value
            for key, value in encode_params.items():
                if value is not None and str(value) != "":
                    defaults[key] = str(value)
        return defaults