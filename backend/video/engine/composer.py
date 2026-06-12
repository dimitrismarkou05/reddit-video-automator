"""FFmpeg video composer with segmented rendering, resource limits, and hwaccel."""

import asyncio
import functools
import logging
import os
import platform
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List, Tuple

from core.config import FFMPEG_PATH
from core.ffmpeg_settings import get_preset_timeout_multiplier
from video.engine.resource_budget import (
    ResourceBudget,
    needs_segmentation,
    segment_count,
    should_prepare_background,
)
from video.engine.subtitles import slice_ass
from video.engine.utils import (
    get_video_info,
    calculate_target_dimensions,
    get_audio_duration,
)

logger = logging.getLogger(__name__)

_PROGRESS_THROTTLE_SEC = 1.0

# Type: (sub_pct, step, optional_status_message)
ProgressCallback = Callable[..., None]


class FFmpegComposerError(Exception):
    pass


@functools.lru_cache(maxsize=4)
def _detect_hwaccel_encoder(ffmpeg_path: str) -> Optional[str]:
    """Return the best available hardware H.264 encoder, or None for software.

    Result is cached per ffmpeg_path so we only probe once per process.
    """
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


def _subprocess_popen_kwargs(use_low_priority: bool = True) -> dict:
    """Lower priority only when RAM is tight so encode stays fast when headroom exists."""
    if not use_low_priority:
        return {}
    kwargs: dict = {}
    if platform.system().lower() == "windows":
        kwargs["creationflags"] = subprocess.BELOW_NORMAL_PRIORITY_CLASS  # type: ignore[attr-defined]
    else:
        # lambda defers os.nice() until the child process is forked so we do
        # not deprioritise the parent backend process.
        kwargs["preexec_fn"] = lambda: os.nice(10)  # type: ignore[assignment]
    return kwargs


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
        progress_callback: Optional[ProgressCallback] = None,
        encode_params: Optional[Dict[str, Any]] = None,
        use_hwaccel: bool = False,
        resource_budget: Optional[ResourceBudget] = None,
    ) -> float:
        if audio_duration is None:
            audio_duration = get_audio_duration(audio_path)

        budget = resource_budget or ResourceBudget(
            ffmpeg_threads=4,
            filter_threads=2,
            segment_duration_sec=180,
            use_single_pass=True,
            total_ram_gb=8.0,
            available_ram_gb=3.0,
            use_low_priority=False,
        )

        work_dir = Path(output_path).parent / "_compose_work"
        bg_input = background_video
        prepared = False

        # Only pre-render the background when we will actually use multiple
        # segments — it amortises the extra encode across them.  In single-pass
        # mode the scale+crop+subtitle filter graph handles everything in one
        # FFmpeg invocation, so a separate prepare step is pure waste (and
        # introduces an extra lossy transcode).
        if should_prepare_background(audio_duration) and needs_segmentation(audio_duration, budget):
            work_dir.mkdir(parents=True, exist_ok=True)
            prep_path = work_dir / "background_prepared.mp4"
            await asyncio.to_thread(
                self._prepare_background,
                background_video,
                str(prep_path),
                video_format,
                audio_duration,
                budget,
            )
            bg_input = str(prep_path)
            prepared = True

        try:
            if needs_segmentation(audio_duration, budget):
                total_segs = segment_count(audio_duration, budget)
                logger.info(
                    "[Composer] Segmented compose: %d segment(s) of ~%ds",
                    total_segs,
                    budget.segment_duration_sec,
                )
                return await self._compose_segmented(
                    bg_input,
                    audio_path,
                    subtitle_path,
                    output_path,
                    video_format,
                    audio_duration,
                    progress_callback,
                    encode_params,
                    use_hwaccel,
                    budget,
                    prepared_background=prepared,
                    work_dir=work_dir,
                )

            return await self._compose_single(
                bg_input,
                audio_path,
                subtitle_path,
                output_path,
                video_format,
                audio_duration,
                progress_callback,
                encode_params,
                use_hwaccel,
                budget,
                segment_index=1,
                segment_total=1,
                prepared_background=prepared,
            )
        finally:
            if work_dir.exists():
                for p in work_dir.glob("*"):
                    try:
                        p.unlink()
                    except OSError:
                        pass
                try:
                    work_dir.rmdir()
                except OSError:
                    pass

    def _prepare_background(
        self,
        background_video: str,
        output_path: str,
        video_format: str,
        duration: float,
        budget: ResourceBudget,
    ) -> None:
        """One-time loop+scale+crop pass; segments only burn subtitles + final encode."""
        target_w, target_h = calculate_target_dimensions(video_format)
        filter_complex = (
            f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h}[v]"
        )
        cmd = [
            self.ffmpeg_path, "-y",
            "-threads", str(budget.ffmpeg_threads),
            "-filter_threads", str(budget.filter_threads),
            "-stream_loop", "-1",
            "-i", background_video,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        timeout = max(300, int(duration * 5))
        self._run_simple_ffmpeg(cmd, budget, timeout=timeout)
        logger.info("[Composer] Background prepared: %s", output_path)

    async def _compose_segmented(
        self,
        background_video: str,
        audio_path: str,
        subtitle_path: Optional[str],
        output_path: str,
        video_format: str,
        audio_duration: float,
        progress_callback: Optional[ProgressCallback],
        encode_params: Optional[Dict[str, Any]],
        use_hwaccel: bool,
        budget: ResourceBudget,
        prepared_background: bool = False,
        work_dir: Optional[Path] = None,
    ) -> float:
        out = Path(output_path)
        work_dir = work_dir or (out.parent / "_compose_work")
        work_dir.mkdir(parents=True, exist_ok=True)
        seg_dur = budget.segment_duration_sec
        total_segs = segment_count(audio_duration, budget)
        segment_paths: List[Path] = []

        try:
            for idx in range(total_segs):
                t_start = idx * seg_dur
                t_end = min(audio_duration, (idx + 1) * seg_dur)
                seg_len = t_end - t_start
                if seg_len <= 0:
                    continue

                seg_audio = work_dir / f"audio_{idx:04d}.wav"
                seg_sub: Optional[Path] = None
                seg_out = work_dir / f"segment_{idx:04d}.mp4"

                await asyncio.to_thread(
                    self._slice_audio,
                    audio_path,
                    str(seg_audio),
                    t_start,
                    seg_len,
                    budget,
                )

                if subtitle_path and Path(subtitle_path).exists():
                    seg_sub = work_dir / f"subs_{idx:04d}.ass"
                    await asyncio.to_thread(
                        slice_ass,
                        Path(subtitle_path),
                        seg_sub,
                        t_start,
                        t_end,
                    )

                def seg_progress(pct: int, _step: str, msg: Optional[str] = None) -> None:
                    if not progress_callback:
                        return
                    overall = int(((idx + pct / 100.0) / total_segs) * 100)
                    message = msg or f"Rendering segment {idx + 1}/{total_segs}"
                    progress_callback(overall, "compositing", message)

                await self._compose_single(
                    background_video,
                    str(seg_audio),
                    str(seg_sub) if seg_sub else None,
                    str(seg_out),
                    video_format,
                    seg_len,
                    seg_progress,
                    encode_params,
                    use_hwaccel,
                    budget,
                    segment_index=idx + 1,
                    segment_total=total_segs,
                    prepared_background=prepared_background,
                    bg_seek_start=t_start if prepared_background else 0.0,
                )
                segment_paths.append(seg_out)

            await asyncio.to_thread(
                self._concat_segments,
                segment_paths,
                output_path,
                budget,
            )

            if progress_callback:
                progress_callback(100, "compositing", "Rendering complete")

            out_duration, _, _ = get_video_info(output_path)
            return out_duration
        finally:
            for p in segment_paths:
                p.unlink(missing_ok=True)

    def _slice_audio(
        self,
        audio_path: str,
        output_path: str,
        start_sec: float,
        duration_sec: float,
        budget: ResourceBudget,
    ) -> None:
        cmd = [
            self.ffmpeg_path, "-y",
            "-threads", str(budget.ffmpeg_threads),
            "-ss", str(start_sec),
            "-t", str(duration_sec),
            "-i", audio_path,
            "-acodec", "pcm_s16le",
            "-ar", "22050",
            "-ac", "1",
            output_path,
        ]
        self._run_simple_ffmpeg(cmd, budget, timeout=120)

    def _concat_segments(
        self,
        parts: List[Path],
        output_path: str,
        budget: ResourceBudget,
    ) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as flist:
            for p in parts:
                fwd = str(p).replace("\\", "/").replace("'", "\\'")
                flist.write(f"file '{fwd}'\n")
            list_path = flist.name

        cmd = [
            self.ffmpeg_path, "-y",
            "-threads", str(budget.ffmpeg_threads),
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            output_path,
        ]
        try:
            self._run_simple_ffmpeg(cmd, budget, timeout=300)
        finally:
            Path(list_path).unlink(missing_ok=True)

    def _run_simple_ffmpeg(
        self,
        cmd: List[str],
        budget: ResourceBudget,
        timeout: int = 600,
    ) -> None:
        self._cancelled = False
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **_subprocess_popen_kwargs(budget.use_low_priority),
        )
        self._process = proc
        try:
            _, stderr = proc.communicate(timeout=timeout)
            if proc.returncode != 0:
                raise FFmpegComposerError(
                    f"FFmpeg failed: {stderr[-2000:] if stderr else proc.returncode}"
                )
            if self._cancelled:
                raise FFmpegComposerError("FFmpeg composition was cancelled")
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise FFmpegComposerError(f"FFmpeg timed out after {timeout}s")
        finally:
            self._process = None

    def _build_filter_complex(
        self,
        video_format: str,
        subtitle_path: Optional[str],
        prepared_background: bool,
    ) -> str:
        if prepared_background:
            if subtitle_path and Path(subtitle_path).exists():
                sub_path = str(subtitle_path).replace("\\", "/")
                if ":" in sub_path:
                    sub_path = sub_path.replace(":", "\\:", 1)
                return f"[0:v]subtitles=filename='{sub_path}'[v]"
            return "[0:v]copy[v]"

        target_w, target_h = calculate_target_dimensions(video_format)
        base_filter = (
            f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h}"
        )
        if subtitle_path and Path(subtitle_path).exists():
            sub_path = str(subtitle_path).replace("\\", "/")
            if ":" in sub_path:
                sub_path = sub_path.replace(":", "\\:", 1)
            return f"{base_filter},subtitles=filename='{sub_path}'[v]"
        return f"{base_filter}[v]"

    async def _compose_single(
        self,
        background_video: str,
        audio_path: str,
        subtitle_path: Optional[str],
        output_path: str,
        video_format: str,
        segment_duration: float,
        progress_callback: Optional[ProgressCallback],
        encode_params: Optional[Dict[str, Any]],
        use_hwaccel: bool,
        budget: ResourceBudget,
        segment_index: int = 1,
        segment_total: int = 1,
        prepared_background: bool = False,
        bg_seek_start: float = 0.0,
    ) -> float:
        if not prepared_background:
            get_video_info(background_video)

        filter_complex = self._build_filter_complex(
            video_format, subtitle_path, prepared_background
        )

        params = self._resolve_encode_params(encode_params)
        video_codec = params["video_codec"]
        if use_hwaccel and video_codec == "libx264":
            hw = _detect_hwaccel_encoder(self.ffmpeg_path)
            if hw:
                video_codec = hw
                logger.info(f"[Composer] Using hw encoder: {hw}")

        cmd = [
            self.ffmpeg_path, "-y",
            "-threads", str(budget.ffmpeg_threads),
            "-filter_threads", str(budget.filter_threads),
        ]
        if prepared_background and bg_seek_start > 0:
            cmd.extend(["-ss", str(bg_seek_start)])
        if not prepared_background:
            cmd.extend(["-stream_loop", "-1"])
        cmd.extend([
            "-i", background_video,
            "-i", audio_path,
            "-progress", "pipe:1",
            "-nostats",
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", video_codec,
            "-preset", params["preset"],
        ])

        if video_codec == "libx264":
            cmd.extend(["-x264-params", "rc-lookahead=20"])

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
            "-t", str(segment_duration),
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
            int(segment_duration * 20 * timeout_multiplier) + 120,
        )

        status_msg = (
            f"Rendering segment {segment_index}/{segment_total}"
            if segment_total > 1
            else "Rendering video"
        )

        def run_ffmpeg() -> Tuple[int, str]:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                **_subprocess_popen_kwargs(budget.use_low_priority),
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
                progress_callback(percent, "compositing", status_msg)

            def drain_stderr() -> None:
                while True:
                    chunk = self._process.stderr.read(512)  # type: ignore[union-attr]
                    if not chunk:
                        break
                    stderr_lines.append(chunk)
                    if self._cancelled:
                        return

            def parse_stdout() -> None:
                for line in self._process.stdout:  # type: ignore[union-attr]
                    line = line.strip()
                    if self._cancelled:
                        break
                    if line.startswith("out_time_us="):
                        try:
                            us = int(line.split("=", 1)[1])
                            if segment_duration > 0:
                                pct = min(
                                    int((us / 1_000_000 / segment_duration) * 100),
                                    99,
                                )
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

            return returncode, "".join(stderr_lines)

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
                    if key in defaults:
                        defaults[key] = str(value)
        return defaults
