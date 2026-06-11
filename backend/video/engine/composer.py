"""FFmpeg video composer with structured progress, hwaccel support, and hard timeout."""

import asyncio
import logging
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

logger = logging.getLogger(__name__)

_PROGRESS_THROTTLE_SEC = 1.0


class FFmpegComposerError(Exception):
    pass


def _detect_hwaccel_encoder(ffmpeg_path: str) -> Optional[str]:
    """Return the best available hardware H.264 encoder, or None for software."""
    try:
        result = subprocess.run(
            [ffmpeg_path, "-encoders", "-hide_banner"],
            capture_output=True, text=True, timeout=5,
        )
        enc = result.stdout
        for name in ("h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox"):
            if name in enc:
                logger.info(f"[Composer] Hardware encoder available: {name}")
                return name
    except Exception as exc:
        logger.debug(f"[Composer] hwaccel probe failed: {exc}")
    return None


class FFmpegComposer:
    def __init__(self, ffmpeg_path: str = FFMPEG_PATH):
        self.ffmpeg_path = ffmpeg_path
        self._process: Optional[subprocess.Popen] = None
        self._cancelled = False

    def cancel(self) -> None:
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
        use_hwaccel: bool = False,
    ) -> float:
        target_w, target_h = calculate_target_dimensions(video_format)
        get_video_info(background_video)

        if audio_duration is None:
            audio_duration = get_audio_duration(audio_path)
        final_duration = audio_duration

        # Build subtitle filter.
        base_filter = (
            f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h}"
        )
        if subtitle_path and Path(subtitle_path).exists():
            sub_path = str(subtitle_path).replace("\\", "/")
            if ":" in sub_path:
                sub_path = sub_path.replace(":", "\\:", 1)
            filter_complex = f"{base_filter},subtitles=filename='{sub_path}'[v]"
        else:
            filter_complex = f"{base_filter}[v]"

        params = self._resolve_encode_params(encode_params)

        # Hardware encoder override.
        video_codec = params["video_codec"]
        if use_hwaccel and video_codec == "libx264":
            hw = _detect_hwaccel_encoder(self.ffmpeg_path)
            if hw:
                video_codec = hw
                logger.info(f"[Composer] Using hw encoder: {hw}")

        cmd = [
            self.ffmpeg_path, "-y",
            "-stream_loop", "-1",
            "-i", background_video,
            "-i", audio_path,
            "-progress", "pipe:1",  # structured progress to stdout
            "-nostats",
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", video_codec,
            "-preset", params["preset"],
        ]

        if params.get("crf"):
            cmd.extend(["-crf", str(params["crf"])])
        elif params.get("video_bitrate"):
            cmd.extend(["-b:v", str(params["video_bitrate"])])
        else:
            cmd.extend(["-crf", "23"])

        cmd.extend([
            "-c:a", params["audio_codec"],
            "-b:a", params["audio_bitrate"],
            "-ar", params["audio_sample_rate"],
            "-shortest",
            "-t", str(final_duration),
            "-pix_fmt", params["pixel_format"],
            "-movflags", "+faststart",
            output_path,
        ])

        self._cancelled = False
        self._process = None

        preset = params.get("preset", "veryfast")
        timeout_multiplier = get_preset_timeout_multiplier(preset)
        compose_timeout = max(
            600,
            int(final_duration * 20 * timeout_multiplier) + 120,
        )

        def run_ffmpeg():
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            last_progress = 0
            last_callback_time = 0.0
            progress_lock = threading.Lock()
            stderr_lines: list[str] = []

            def report(percent: int, force: bool = False) -> None:
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
                """Read stderr to prevent pipe stall; collect for error reporting."""
                while True:
                    chunk = self._process.stderr.read(512)  # type: ignore[union-attr]
                    if not chunk:
                        break
                    stderr_lines.append(chunk)
                    if self._cancelled:
                        return

            def parse_stdout() -> None:
                """Parse -progress pipe:1 key=value output from stdout."""
                for line in self._process.stdout:  # type: ignore[union-attr]
                    line = line.strip()
                    if self._cancelled:
                        break
                    if line.startswith("out_time_us="):
                        try:
                            us = int(line.split("=", 1)[1])
                            if final_duration > 0:
                                pct = min(int((us / 1_000_000 / final_duration) * 100), 99)
                                report(pct)
                        except (ValueError, ZeroDivisionError):
                            pass
                    elif line == "progress=end":
                        report(100, force=True)

            stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
            stderr_thread.start()
            stdout_thread = threading.Thread(target=parse_stdout, daemon=True)
            stdout_thread.start()

            try:
                returncode = self._process.wait(timeout=compose_timeout)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
                raise FFmpegComposerError(
                    f"FFmpeg timed out after {compose_timeout}s"
                )
            finally:
                stderr_thread.join(timeout=10)
                stdout_thread.join(timeout=5)

            if self._cancelled:
                raise FFmpegComposerError("FFmpeg composition was cancelled")

            stderr = "".join(stderr_lines)
            return returncode, stderr

        try:
            returncode, stderr = await asyncio.to_thread(run_ffmpeg)
            if returncode != 0:
                logger.error(f"[Composer] FFmpeg stderr:\n{stderr}")
                raise FFmpegComposerError(
                    f"FFmpeg exited with code {returncode}. See logs."
                )

            out_duration, _, _ = get_video_info(output_path)
            return out_duration
        except FFmpegComposerError:
            raise
        except Exception as exc:
            raise FFmpegComposerError(f"FFmpeg composition error: {exc}")
        finally:
            self._process = None

    def _resolve_encode_params(self, encode_params: Optional[Dict[str, Any]]) -> Dict[str, str]:
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
            for key, value in encode_params.items():
                if value is not None and str(value) != "":
                    defaults[key] = str(value)
        return defaults
