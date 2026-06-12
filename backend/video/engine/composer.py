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

    Two-phase check: first confirms the encoder is compiled in, then does a
    0.1-second test encode to verify the driver is actually usable (e.g. NVENC
    is listed even without CUDA drivers installed, causing a runtime failure).
    Result is cached per ffmpeg_path so we only probe once per process.
    """
    try:
        result = subprocess.run(
            [ffmpeg_path, "-encoders", "-hide_banner"],
            capture_output=True, text=True, timeout=5,
        )
        enc = result.stdout
        for name in ("h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox"):
            if name not in enc:
                continue
            # Attempt a minimal test encode — fails instantly if the driver is
            # missing, succeeds in <1 s when the hardware is genuinely available.
            test = subprocess.run(
                [
                    ffmpeg_path, "-y",
                    "-f", "lavfi", "-i", "color=c=black:size=64x64:duration=0.1",
                    "-c:v", name,
                    "-f", "null", "-",
                ],
                capture_output=True, text=True, timeout=15,
            )
            if test.returncode == 0:
                logger.info(f"[Composer] Hardware encoder validated and available: {name}")
                return name
            logger.debug(
                f"[Composer] Hardware encoder {name} listed but not usable "
                f"(driver/init failure): {test.stderr[-300:]}"
            )
    except Exception as exc:
        logger.debug(f"[Composer] hwaccel probe failed: {exc}")
    return None


# ---------------------------------------------------------------------------
# Hardware-encoder quality-parameter translation
# ---------------------------------------------------------------------------

# Map x264 preset names to NVENC p-levels (p1=fastest … p7=slowest).
_HW_PRESET_MAP_NVENC: Dict[str, str] = {
    "ultrafast": "p1", "superfast": "p2", "veryfast": "p3", "faster": "p4",
    "fast": "p4", "medium": "p5", "slow": "p6", "slower": "p7", "veryslow": "p7",
}

# QSV does not support "ultrafast"/"superfast" — map those to "veryfast".
_QSV_UNSUPPORTED = frozenset({"ultrafast", "superfast"})


def _hw_quality_args(hw: str, preset: str = "veryfast", crf: str = "23") -> List[str]:
    """Translate x264 preset/CRF into the correct quality args for *hw* encoder.

    Returns a list of FFmpeg argument tokens ready to extend a command list.
    Falls back to software args for any unrecognised encoder name so that new
    hardware encoders added to _detect_hwaccel_encoder are handled safely.
    """
    if hw == "h264_nvenc":
        return [
            "-preset", _HW_PRESET_MAP_NVENC.get(preset, "p4"),
            "-rc", "vbr",
            "-cq", str(crf),
            "-b:v", "0",
        ]
    if hw == "h264_qsv":
        qsv_preset = "veryfast" if preset in _QSV_UNSUPPORTED else preset
        return ["-preset", qsv_preset, "-global_quality", str(crf)]
    if hw == "h264_amf":
        return [
            "-quality", "speed",
            "-rc", "cqp",
            "-qp_i", str(crf),
            "-qp_p", str(crf),
        ]
    if hw == "h264_videotoolbox":
        # videotoolbox uses -q:v 1-100 (lower = better quality).
        # Map CRF 0-51 linearly to q:v 1-100.
        try:
            q = max(1, min(100, int(int(crf) * 100 // 51)))
        except (ValueError, ZeroDivisionError):
            q = 45
        return ["-q:v", str(q)]
    # Unknown hw encoder — fall back to x264-compatible args.
    return ["-preset", preset, "-crf", str(crf)]


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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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

        try:
            if needs_segmentation(audio_duration, budget):
                total_segs = segment_count(audio_duration, budget)
                logger.info(
                    "[Composer] Segmented compose: %d segment(s) of ~%ds",
                    total_segs,
                    budget.segment_duration_sec,
                )
                return await self._compose_segmented(
                    background_video,
                    audio_path,
                    subtitle_path,
                    output_path,
                    video_format,
                    audio_duration,
                    progress_callback,
                    encode_params,
                    use_hwaccel,
                    budget,
                    work_dir=work_dir,
                )

            return await self._compose_single(
                background_video,
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
                final_output=True,
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

    # ------------------------------------------------------------------
    # Reusable FFmpeg runner with live progress
    # ------------------------------------------------------------------

    def _run_ffmpeg_with_progress(
        self,
        cmd: List[str],
        budget: ResourceBudget,
        segment_duration: float,
        progress_callback: Optional[ProgressCallback],
        status_msg: str,
        timeout: int = 600,
    ) -> None:
        """Spawn FFmpeg with ``-progress pipe:1`` and stream progress to *callback*.

        Designed to be called from a worker thread (via asyncio.to_thread).
        """
        self._cancelled = False
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            **_subprocess_popen_kwargs(budget.use_low_priority),
        )
        self._process = proc

        last_progress = 0
        last_callback_time = 0.0
        progress_lock = threading.Lock()
        stderr_lines: List[str] = []

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
                chunk = proc.stderr.read(512)  # type: ignore[union-attr]
                if not chunk:
                    break
                stderr_lines.append(chunk)
                if self._cancelled:
                    return

        def parse_stdout() -> None:
            for line in proc.stdout:  # type: ignore[union-attr]
                line = line.strip()
                if self._cancelled:
                    break
                if line.startswith("out_time_us="):
                    try:
                        us = int(line.split("=", 1)[1])
                        if segment_duration > 0:
                            pct = min(int((us / 1_000_000 / segment_duration) * 100), 99)
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
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise FFmpegComposerError(f"FFmpeg timed out after {timeout}s")
        finally:
            stderr_thread.join(timeout=10)
            stdout_thread.join(timeout=5)
            self._process = None

        if self._cancelled:
            raise FFmpegComposerError("FFmpeg composition was cancelled")
        if returncode != 0:
            err = "".join(stderr_lines)
            raise FFmpegComposerError(
                f"FFmpeg failed: {err[-2000:] if err else returncode}"
            )

    # ------------------------------------------------------------------
    # Segmented compose
    # ------------------------------------------------------------------

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
        work_dir: Optional[Path] = None,
    ) -> float:
        out = Path(output_path)
        work_dir = work_dir or (out.parent / "_compose_work")
        work_dir.mkdir(parents=True, exist_ok=True)
        seg_dur = budget.segment_duration_sec
        total_segs = segment_count(audio_duration, budget)
        segment_paths: List[Path] = []

        # Probe background duration once so each segment can seek to the
        # correct offset within the looped source (t_start % bg_dur).
        bg_dur, _, _ = await asyncio.to_thread(get_video_info, background_video)

        try:
            for idx in range(total_segs):
                t_start = idx * seg_dur
                t_end = min(audio_duration, (idx + 1) * seg_dur)
                seg_len = t_end - t_start
                if seg_len <= 0:
                    continue

                seg_sub: Optional[Path] = None
                seg_out = work_dir / f"segment_{idx:04d}.mp4"

                if subtitle_path and Path(subtitle_path).exists():
                    seg_sub = work_dir / f"subs_{idx:04d}.ass"
                    await asyncio.to_thread(
                        slice_ass,
                        Path(subtitle_path),
                        seg_sub,
                        t_start,
                        t_end,
                    )

                # Seek background to the position it would have reached in the
                # continuous looped timeline at t_start (modulo bg duration).
                bg_seek = (t_start % bg_dur) if bg_dur > 0 else 0.0

                # Use a default-arg capture of idx so the closure is correct
                # even though this loop is sequential (defensive pattern).
                def seg_progress(
                    pct: int,
                    _step: str,
                    msg: Optional[str] = None,
                    _idx: int = idx,
                ) -> None:
                    if not progress_callback:
                        return
                    overall = int(((_idx + pct / 100.0) / total_segs) * 100)
                    message = msg or f"Rendering segment {_idx + 1}/{total_segs}"
                    progress_callback(overall, "compositing", message)

                await self._compose_single(
                    background_video,
                    audio_path,       # master audio; seek applied inside compose_single
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
                    bg_seek_start=bg_seek,
                    audio_seek_start=t_start,   # inline seek replaces _slice_audio
                    final_output=False,          # skip faststart + probe on segments
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

    # ------------------------------------------------------------------
    # Segment concatenation
    # ------------------------------------------------------------------

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
            "-movflags", "+faststart",   # applied once on the final concat output
            output_path,
        ]
        try:
            self._run_simple_ffmpeg(cmd, budget, timeout=300)
        finally:
            Path(list_path).unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Simple fire-and-forget FFmpeg runner (no progress needed)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Filter-complex builder
    # ------------------------------------------------------------------

    def _build_filter_complex(
        self,
        video_format: str,
        subtitle_path: Optional[str],
    ) -> str:
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

    # ------------------------------------------------------------------
    # Single-pass compose (used for full video OR one segment)
    # ------------------------------------------------------------------

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
        bg_seek_start: float = 0.0,
        audio_seek_start: float = 0.0,
        final_output: bool = True,
    ) -> float:
        """Encode one video (or one segment).

        *bg_seek_start* positions the looped background at the correct offset so
        the visual background appears continuous across segments without a
        separate prepare pass.  For segment N: bg_seek_start = (N*seg_dur) % bg_dur.

        *audio_seek_start* seeks the master audio inline with ``-ss`` instead of
        writing a trimmed WAV per segment.

        *final_output=False* skips ``-movflags +faststart`` (moov relocation) and
        the post-encode ffprobe on intermediate segment files that are discarded
        after concat — pure saved I/O.
        """
        filter_complex = self._build_filter_complex(video_format, subtitle_path)

        params = self._resolve_encode_params(encode_params)
        video_codec = params["video_codec"]
        hw_encoder: Optional[str] = None
        if use_hwaccel and video_codec == "libx264":
            hw = _detect_hwaccel_encoder(self.ffmpeg_path)
            if hw:
                video_codec = hw
                hw_encoder = hw
                logger.info(f"[Composer] Using hw encoder: {hw}")

        # ---- Build FFmpeg command ----------------------------------------
        cmd = [
            self.ffmpeg_path, "-y",
            "-threads", str(budget.ffmpeg_threads),
            "-filter_threads", str(budget.filter_threads),
        ]

        # --- Video input ---
        # Seek to the background position for this segment before the loop
        # starts; subsequent loop iterations restart at 0, giving a continuous
        # looped timeline without an expensive prepare pass.
        if bg_seek_start > 0:
            cmd.extend(["-ss", str(bg_seek_start)])
        cmd.extend(["-stream_loop", "-1"])
        # Hardware decode hint: 'auto' tries the hw surface and falls back to
        # software on unsupported configurations — always safe to include.
        if hw_encoder:
            cmd.extend(["-hwaccel", "auto"])
        cmd.extend(["-i", background_video])

        # --- Audio input (inline seek replaces a separate _slice_audio pass) ---
        if audio_seek_start > 0:
            cmd.extend(["-ss", str(audio_seek_start)])
        cmd.extend(["-i", audio_path])

        # --- Filter + stream mapping ---
        cmd.extend([
            "-progress", "pipe:1",
            "-nostats",
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", video_codec,
        ])

        # --- Video quality args (hw vs. software) ---
        if hw_encoder:
            cmd.extend(_hw_quality_args(hw_encoder, params["preset"], str(params.get("crf", "23"))))
        else:
            cmd.extend(["-preset", params["preset"]])
            if params.get("crf"):
                cmd.extend(["-crf", str(params["crf"])])
            elif params.get("video_bitrate"):
                cmd.extend(["-b:v", str(params["video_bitrate"])])
            else:
                cmd.extend(["-crf", "23"])

        # --- Audio + output ---
        cmd.extend([
            "-c:a", params["audio_codec"],
            "-b:a", params["audio_bitrate"],
            "-ar", params["audio_sample_rate"],
            "-shortest",
            "-t", str(segment_duration),
            "-pix_fmt", params["pixel_format"],
        ])

        # faststart moves the moov atom to the front for streaming; skip on
        # intermediate segments since they are discarded after concat anyway.
        if final_output:
            cmd.extend(["-movflags", "+faststart"])

        cmd.append(output_path)

        # ---- Timeouts -------------------------------------------------------
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

        # ---- Threaded FFmpeg runner ------------------------------------------
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

            # Only probe for real duration on the final output file.
            # For intermediate segments the exact target duration is already
            # known, saving one ffprobe subprocess per segment.
            if final_output:
                out_duration, _, _ = get_video_info(output_path)
                return out_duration
            return segment_duration
        except FFmpegComposerError:
            raise
        except Exception as exc:
            raise FFmpegComposerError(f"FFmpeg composition error: {exc}")
        finally:
            self._process = None

    # ------------------------------------------------------------------
    # Encode-parameter resolver
    # ------------------------------------------------------------------

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
