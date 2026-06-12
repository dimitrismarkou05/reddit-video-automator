"""Video generation pipeline with continuous weighted progress and push-based SSE."""

import asyncio
import gc
import json
import logging
import re
import shutil
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, List

from sqlalchemy.orm import Session

from stories.models import Story, StoryStatus
from video.models import GeneratedVideo, VideoStatus
from stories.linker.core import UpdateLinker
from video.engine.tts import TTSEngine, TTSProviderError
from video.engine.subtitles import SubtitleGenerator
from video.engine.composer import FFmpegComposer, FFmpegComposerError
from video.engine.thumbnail import ThumbnailGenerator
from video.engine.utils import (
    get_output_folder,
    get_temp_folder,
    cleanup_temp,
    select_background_video,
)
from video.schemas import SubtitleStyle
from notifications.sse import notification_queue
from ffmpeg import ensure_ffmpeg_in_path
import video.engine.progress_push as progress_push

logger = logging.getLogger(__name__)


class VideoPipelineError(Exception):
    pass


class PipelineCancelledError(Exception):
    pass


class PipelinePausedError(Exception):
    pass


# ---------------------------------------------------------------------------
# Continuous weighted progress ranges (lo, hi) — monotonically increasing.
# sub_pct (0-100) maps linearly within (lo, hi).
# ---------------------------------------------------------------------------
STAGE_RANGES: dict[str, tuple[int, int]] = {
    "preparing":             (0,   2),
    "downloading_model":     (2,   10),
    "tts_synthesizing":      (10,  35),
    "tts_done":              (35,  35),
    "transcribing":          (35,  55),
    "transcribe_done":       (55,  55),
    "generating_subtitles":  (55,  58),
    "subtitles_done":        (58,  58),
    "selecting_background":  (58,  60),
    "compositing":           (60,  97),
    "compositing_done":      (97,  97),
    "generating_thumbnail":  (97,  99),
    "done":                  (100, 100),
    "failed":                (0,   0),
}

_STEP_MESSAGES: dict[str, str] = {
    "preparing":             "Preparing script",
    "downloading_model":     "Loading voice model",
    "tts_synthesizing":      "Generating voice",
    "tts_done":              "Voice ready",
    "transcribing":          "Transcribing audio",
    "transcribe_done":       "Transcription complete",
    "generating_subtitles":  "Building subtitles",
    "subtitles_done":        "Subtitles ready",
    "selecting_background":  "Selecting background",
    "compositing":           "Rendering video",
    "compositing_done":      "Video rendered",
    "generating_thumbnail":  "Creating thumbnail",
    "done":                  "Complete",
    "failed":                "Generation failed",
}


class VideoPipeline:
    def __init__(self, db: Session, ffmpeg_path: str = "ffmpeg"):
        self.db = db
        self.ffmpeg_path = ffmpeg_path
        self.composer = FFmpegComposer(ffmpeg_path)
        whisper_size = _get_whisper_model_size(db)
        self.subtitle_gen = SubtitleGenerator(model_size=whisper_size)
        self.thumbnail_gen = ThumbnailGenerator()
        self._cancelled = False
        self._paused = False
        self._progress_callback: Optional[Callable[[int, str], None]] = None
        self._throttle_at: dict[str, float] = {}
        self._throttle_pct: dict[str, int] = {}
        self._status_message_override: Optional[str] = None

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def _update_progress(
        self,
        video_record: GeneratedVideo,
        step: str,
        sub_pct: int = 0,
        callback: Optional[Callable[[int, str], None]] = None,
        throttle_sec: float = 0.0,
        force: bool = False,
        status_message: Optional[str] = None,
    ) -> None:
        """Commit progress to DB and push to SSE channel."""
        if status_message is not None:
            self._status_message_override = status_message
        elif step != (video_record.current_step or ""):
            self._status_message_override = None
        try:
            lo, hi = STAGE_RANGES.get(step, (0, 0))
            raw = lo + int((hi - lo) * max(0, min(sub_pct, 100)) / 100)
            new_pct = min(raw, 99) if step != "done" else 100

            # Monotonic: never decrease.
            prev = video_record.progress_percent or 0
            if new_pct < prev:
                new_pct = prev

            if throttle_sec > 0 and not force:
                key = f"{video_record.id}:{step}"
                now = time.monotonic()
                if (
                    now - self._throttle_at.get(key, 0.0) < throttle_sec
                    and new_pct <= self._throttle_pct.get(key, -1) + 1
                ):
                    return
                self._throttle_at[key] = now
                self._throttle_pct[key] = new_pct

            video_record.progress_percent = new_pct
            video_record.current_step = step
            video_record.step_progress = sub_pct
            video_record.last_progress_at = datetime.now(timezone.utc)
            video_record.status_message = (
                self._status_message_override
                or _STEP_MESSAGES.get(step, step)
            )
            self.db.commit()

            # Push to SSE immediately.
            payload = _build_progress_payload(
                video_record,
                step,
                self._status_message_override,
            )
            progress_push.push_progress(video_record.id, payload)

            logger.debug(f"[Pipeline {video_record.id}] {step} {new_pct}%")

            if callback:
                try:
                    callback(new_pct, step)
                except Exception as cb_err:
                    logger.warning(
                        f"[Pipeline {video_record.id}] Progress callback error: {cb_err}"
                    )
        except Exception as db_err:
            logger.error(
                f"[Pipeline {video_record.id}] DB progress update error: {db_err}"
            )

    async def _run_in_thread_with_heartbeat(
        self,
        video_record: GeneratedVideo,
        step: str,
        fn: Callable,
        *args,
        heartbeat_callback: Optional[Callable[[int, str], None]] = None,
        heartbeat_interval: float = 15.0,
        max_sub_pct: int = 90,
        **fn_kwargs,
    ):
        """Run blocking work in a thread, emitting heartbeat progress updates."""
        task = asyncio.create_task(asyncio.to_thread(fn, *args, **fn_kwargs))
        heartbeat_idx = 0
        while not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=heartbeat_interval)
                break
            except asyncio.TimeoutError:
                heartbeat_idx = min(heartbeat_idx + 5, max_sub_pct)
                self._update_progress(
                    video_record, step, heartbeat_idx,
                    heartbeat_callback, throttle_sec=heartbeat_interval * 0.9,
                )
        return await task

    # ------------------------------------------------------------------
    # Checkpoint
    # ------------------------------------------------------------------

    def _save_checkpoint(
        self, video_record: GeneratedVideo, step: str, temp_data: dict
    ) -> None:
        try:
            payload = {**temp_data, "step": step}
            video_record.current_step = step
            video_record.temp_files_json = payload
            self.db.commit()
        except Exception as exc:
            logger.error(f"[Pipeline {video_record.id}] Checkpoint save error: {exc}")

    def _load_checkpoint(self, video_record: GeneratedVideo) -> dict:
        from video.engine.checkpoint import build_checkpoint_payload

        checkpoint = build_checkpoint_payload(video_record)
        video_record.temp_files_json = checkpoint
        try:
            self.db.commit()
        except Exception as exc:
            logger.warning(
                f"[Pipeline {video_record.id}] Could not persist sanitized checkpoint: {exc}"
            )
        return checkpoint

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_narrative_text(self, story: Story, include_updates: bool) -> str:
        linker = UpdateLinker(self.db)
        if include_updates:
            return linker.get_full_narrative(story.id, include_inline_updates=True)
        return f"{story.title}. {story.body or ''}"

    def _generate_hashtags(self, text: str) -> List[str]:
        stop_words = {
            "the","a","an","is","are","was","were","be","been","being","have","has",
            "had","do","does","did","will","would","could","should","may","might",
            "must","shall","can","need","to","of","in","for","on","with","at","by",
            "from","as","into","through","during","before","after","above","below",
            "between","under","and","but","or","yet","so","if","because","although",
            "though","while","where","when","that","which","who","whom","what","this",
            "these","those","i","you","he","she","it","we","they","me","him","her",
            "us","them","my","your","his","our","their","i'm","it's","that's",
            "there's","don't","doesn't","didn't","won't","wouldn't","can't","cannot",
        }
        words = text.lower().split()
        freq: dict[str, int] = {}
        for w in words:
            w = re.sub(r"[^\w]", "", w)
            if len(w) > 3 and w not in stop_words:
                freq[w] = freq.get(w, 0) + 1
        top = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:5]
        tags = [f"#{w}" for w, _ in top]
        tags.extend(["#Reddit", "#StoryTime", "#RedditStories"])
        return tags[:8]

    def check_cancelled(self, video_record: GeneratedVideo) -> None:
        if self._cancelled:
            raise PipelineCancelledError("Cancelled")
        try:
            self.db.refresh(video_record)
        except Exception as exc:
            logger.warning(
                f"[Pipeline {video_record.id}] DB refresh error in cancel check: {exc}"
            )
            raise PipelineCancelledError("Cancelled")
        if not self.db.query(GeneratedVideo).filter(
            GeneratedVideo.id == video_record.id
        ).first():
            raise PipelineCancelledError("Cancelled")
        if video_record.status == VideoStatus.CANCELLED.value:
            raise PipelineCancelledError("Cancelled")
        if video_record.status == VideoStatus.PAUSED.value:
            self._paused = True
            raise PipelinePausedError("Paused")

    def cancel(self) -> None:
        self._cancelled = True
        self.composer.cancel()

    def pause(self) -> None:
        self._paused = True
        self.composer.cancel()

    def resume(self) -> None:
        self._paused = False

    def _record_error(
        self, video_record: GeneratedVideo, error: Exception, step: str
    ) -> None:
        raw = str(error)
        if "api key" in raw.lower() or "not configured" in raw.lower():
            friendly = "TTS model not installed. Check Settings."
        elif "tts" in raw.lower() or "TTS" in type(error).__name__:
            friendly = f"Voice generation failed: {raw[:200]}"
        elif "ffmpeg" in raw.lower() or "FFmpeg" in type(error).__name__:
            friendly = "Video rendering failed. Check FFmpeg installation."
        elif "duration" in raw.lower():
            friendly = "Audio processing failed. The TTS output may be corrupted."
        else:
            friendly = f"Generation failed: {raw[:200]}"

        video_record.status = VideoStatus.FAILED.value
        video_record.error_message = friendly
        video_record.error_type = type(error).__name__
        video_record.error_step = step
        video_record.error_traceback = traceback.format_exc()
        video_record.current_step = step
        try:
            self.db.commit()
            # Push failure state to SSE.
            progress_push.push_progress(
                video_record.id,
                _build_progress_payload(video_record, step),
            )
            logger.error(
                f"[Pipeline {video_record.id}] Error at {step}: {friendly}"
            )
        except Exception as exc:
            logger.error(
                f"[Pipeline {video_record.id}] DB error during error recording: {exc}"
            )

    def _get_ffmpeg_encode_params(self) -> dict:
        try:
            from core.ffmpeg_settings import FFmpegSettings
            settings = FFmpegSettings(self.db)
            params = settings.get_effective_encode_params()
            params["quality"] = settings.get_video_quality()
            return params
        except Exception as exc:
            logger.warning(f"[Pipeline] Could not load FFmpeg settings: {exc}")
            return {
                "video_codec": "libx264",
                "preset": "veryfast",
                "crf": "23",
                "pixel_format": "yuv420p",
                "audio_codec": "aac",
                "audio_bitrate": "192k",
                "audio_sample_rate": "44100",
                "quality": "balanced",
            }

    # ------------------------------------------------------------------
    # Main generate coroutine
    # ------------------------------------------------------------------

    async def generate(
        self,
        video_record: GeneratedVideo,
        include_updates: bool = True,
        voice_id: str = "default",
        background_source: str = "",
        video_format: str = "shorts",
        subtitle_style: Optional[SubtitleStyle] = None,
        generate_hashtags: bool = True,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> GeneratedVideo:
        self._progress_callback = progress_callback
        self._cancelled = False
        self._paused = False

        story = self.db.query(Story).filter(Story.id == video_record.story_id).first()
        if not story:
            raise VideoPipelineError(f"Story {video_record.story_id} not found")

        video_id = video_record.id
        output_folder = get_output_folder(story.id, story.title)
        temp_folder = get_temp_folder(video_id)

        if not video_record.video_path:
            video_record.video_path = str(output_folder / "video.mp4")
        if not video_record.thumbnail_path:
            video_record.thumbnail_path = str(output_folder / "thumbnail.jpg")
        self.db.commit()

        encode_params = self._get_ffmpeg_encode_params()
        checkpoint = self._load_checkpoint(video_record)

        logger.info(
            f"[Pipeline {video_id}] Start story={story.id} "
            f"checkpoint={checkpoint.get('step', 'queued')}"
        )

        if not ensure_ffmpeg_in_path():
            raise VideoPipelineError(
                "FFmpeg not found. Please install FFmpeg in Settings."
            )

        t_start = time.monotonic()

        try:
            # ── Preparing ──────────────────────────────────────────────
            if checkpoint.get("step", "queued") in ("queued", "failed"):
                self.check_cancelled(video_record)
                self._update_progress(video_record, "preparing", 0, progress_callback)

                narrative = self._build_narrative_text(story, include_updates)
                if generate_hashtags:
                    tags = self._generate_hashtags(narrative)
                    style_dict = video_record.subtitle_style or {}
                    style_dict["hashtags"] = tags
                    video_record.subtitle_style = style_dict

                video_record.background_source = background_source
                self.db.commit()
                self._save_checkpoint(video_record, "preparing", {})
                self._update_progress(video_record, "preparing", 100, progress_callback)
                logger.info(
                    f"[Pipeline {video_id}] Narrative length={len(narrative)}"
                )
            else:
                narrative = self._build_narrative_text(story, include_updates)

            # ── TTS ────────────────────────────────────────────────────
            audio_path = temp_folder / "narration.wav"
            if checkpoint.get("step", "preparing") in (
                "queued", "preparing", "failed"
            ):
                self.check_cancelled(video_record)
                self._update_progress(
                    video_record, "downloading_model", 0, progress_callback
                )

                tts_engine = TTSEngine(self.db, self.ffmpeg_path)
                tts_stage_t = time.monotonic()

                # Capture the running event loop so the TTS worker thread can
                # schedule DB updates back onto it safely (DB Session is not
                # thread-safe; we must commit only from the event-loop thread).
                _loop = asyncio.get_running_loop()

                def tts_progress(percent: int, step: str) -> None:
                    """Thread-safe progress bridge: schedules DB update in the event loop."""
                    def _apply():
                        if step == "downloading_model":
                            self._update_progress(
                                video_record, "downloading_model", percent,
                                progress_callback, throttle_sec=2.0,
                            )
                        elif step == "tts_synthesizing":
                            self._update_progress(
                                video_record, "tts_synthesizing", percent,
                                progress_callback, throttle_sec=1.0,
                            )
                    try:
                        _loop.call_soon_threadsafe(_apply)
                    except RuntimeError:
                        pass  # loop closed (shutdown)

                try:
                    audio_duration = await asyncio.to_thread(
                        tts_engine.synthesize,
                        narrative,
                        voice_id,
                        audio_path,
                        tts_progress,
                    )
                except Exception as tts_err:
                    logger.error(
                        f"[Pipeline {video_id}] TTS failed: {tts_err}", exc_info=True
                    )
                    raise TTSProviderError(f"TTS failed: {tts_err}")

                logger.info(
                    f"[Pipeline {video_id}] TTS done in "
                    f"{time.monotonic()-tts_stage_t:.1f}s, "
                    f"audio={audio_duration:.1f}s"
                )

                video_record.audio_path = str(audio_path)
                video_record.duration_seconds = audio_duration
                video_record.tts_audio_path = str(audio_path)
                video_record.status = VideoStatus.TTS_DONE.value
                self.db.commit()
                self._save_checkpoint(
                    video_record, "tts_done", {"audio_path": str(audio_path)}
                )
            else:
                audio_path = Path(checkpoint.get("audio_path", str(audio_path)))
                audio_duration = video_record.duration_seconds or 0.0
                logger.info(
                    f"[Pipeline {video_id}] TTS skipped (checkpoint)"
                )

            self._update_progress(video_record, "tts_done", 0, progress_callback)

            # ── Transcription ──────────────────────────────────────────
            # Start background selection concurrently with transcription:
            # both are independent I/O operations and the background probe
            # (ffprobe per file) can take several seconds on a fresh directory.
            _bg_needs_select = checkpoint.get("step", "subtitles_done") in (
                "queued", "preparing", "tts_done", "transcribe_done",
                "subtitles_done", "failed",
            )
            _bg_cached = (
                checkpoint.get("bg_video")
                or video_record.selected_background_video
            )
            _bg_prefetch_task: Optional[asyncio.Task] = None
            if _bg_needs_select and not _bg_cached:
                _bg_prefetch_task = asyncio.create_task(
                    asyncio.to_thread(select_background_video, background_source),
                    name=f"bg_select_{video_id}",
                )

            whisper_result = None
            if checkpoint.get("step", "tts_done") in (
                "queued", "preparing", "tts_done", "failed"
            ):
                self.check_cancelled(video_record)
                self._update_progress(
                    video_record, "transcribing", 0, progress_callback
                )

                trans_t = time.monotonic()
                _loop2 = asyncio.get_running_loop()

                def transcribe_progress(percent: int, step: str) -> None:
                    def _apply():
                        if step == "transcribing":
                            self._update_progress(
                                video_record, "transcribing", percent,
                                progress_callback, throttle_sec=1.0,
                            )
                    try:
                        _loop2.call_soon_threadsafe(_apply)
                    except RuntimeError:
                        pass

                whisper_result = await asyncio.to_thread(
                    self.subtitle_gen.transcribe,
                    str(audio_path),
                    transcribe_progress,
                    audio_duration,
                )
                logger.info(
                    f"[Pipeline {video_id}] Transcription done in "
                    f"{time.monotonic()-trans_t:.1f}s"
                )

                video_record.whisper_result_json = whisper_result
                video_record.status = VideoStatus.TRANSCRIBE_DONE.value
                self.db.commit()
                self._save_checkpoint(
                    video_record, "transcribe_done",
                    {**checkpoint, "whisper_result": True},
                )
            else:
                whisper_result = video_record.whisper_result_json
                logger.info(
                    f"[Pipeline {video_id}] Transcription skipped (checkpoint)"
                )

            self._update_progress(
                video_record, "transcribe_done", 0, progress_callback
            )

            # ── Subtitles ──────────────────────────────────────────────
            subtitle_path = temp_folder / "subtitles.ass"
            if checkpoint.get("step", "transcribe_done") in (
                "queued", "preparing", "tts_done", "transcribe_done", "failed"
            ):
                self.check_cancelled(video_record)
                self._update_progress(
                    video_record, "generating_subtitles", 0, progress_callback
                )

                if whisper_result is None:
                    whisper_result = await asyncio.to_thread(
                        self.subtitle_gen.transcribe, str(audio_path)
                    )

                dims = {"shorts": (1080, 1920), "normal": (1920, 1080)}
                w, h = dims.get(video_format, (1080, 1920))

                await asyncio.to_thread(
                    self.subtitle_gen.generate_ass,
                    whisper_result,
                    subtitle_path,
                    subtitle_style or SubtitleStyle(),
                    w, h,
                )

                video_record.subtitle_path = str(subtitle_path)
                video_record.subtitle_ass_path = str(subtitle_path)
                video_record.status = VideoStatus.SUBTITLES_DONE.value
                self.db.commit()
                self._save_checkpoint(
                    video_record, "subtitles_done",
                    {**checkpoint, "subtitle_path": str(subtitle_path)},
                )
                self._update_progress(
                    video_record, "subtitles_done", 0, progress_callback
                )
                logger.info(f"[Pipeline {video_id}] Subtitles generated")
            else:
                subtitle_path = Path(
                    checkpoint.get("subtitle_path", str(subtitle_path))
                )
                self._update_progress(
                    video_record, "subtitles_done", 0, progress_callback
                )

            # ── Background selection ───────────────────────────────────
            if _bg_needs_select:
                self.check_cancelled(video_record)
                self._update_progress(
                    video_record, "selecting_background", 0, progress_callback
                )
                if _bg_prefetch_task is not None:
                    # Background selection was running concurrently with
                    # transcription — just collect the result.
                    bg_video = await _bg_prefetch_task
                    _bg_prefetch_task = None
                else:
                    bg_video = await asyncio.to_thread(
                        select_background_video, background_source
                    )
                video_record.selected_background_video = bg_video
                self.db.commit()
                self._save_checkpoint(
                    video_record, "selecting_background",
                    {**checkpoint, "bg_video": bg_video},
                )
                logger.info(f"[Pipeline {video_id}] Background: {bg_video}")
            else:
                if _bg_prefetch_task is not None:
                    _bg_prefetch_task.cancel()
                    _bg_prefetch_task = None
                bg_video = (
                    checkpoint.get("bg_video")
                    or video_record.selected_background_video
                )
                if not bg_video:
                    bg_video = await asyncio.to_thread(
                        select_background_video, background_source
                    )

            # ── FFmpeg compositing ─────────────────────────────────────
            if checkpoint.get("step", "selecting_background") in (
                "queued", "preparing", "tts_done", "transcribe_done",
                "subtitles_done", "selecting_background", "failed",
            ):
                self.check_cancelled(video_record)

                output_video = output_folder / "video.mp4"
                if output_video.exists():
                    try:
                        output_video.unlink()
                        logger.info(
                            f"[Pipeline {video_id}] Removed partial video before compositing"
                        )
                    except OSError as exc:
                        logger.warning(
                            f"[Pipeline {video_id}] Could not remove partial video: {exc}"
                        )

                from core.ffmpeg_settings import get_slow_preset_warning
                warn = get_slow_preset_warning(
                    encode_params.get("preset", "veryfast"),
                    encode_params.get("quality", "balanced"),
                )
                if warn:
                    logger.warning(f"[Pipeline {video_id}] {warn}")

                compose_t = time.monotonic()

                import video.engine.tts_registry as tts_registry
                from video.engine.subtitles import unload_whisper_models
                from video.engine.resource_budget import (
                    compute_resource_budget,
                    needs_segmentation,
                    segment_count,
                    get_memory_gb,
                )
                from core.ffmpeg_settings import FFmpegSettings

                ff_settings = FFmpegSettings(self.db)
                try:
                    threads_override = int(ff_settings.get_ffmpeg_threads() or 0)
                except ValueError:
                    threads_override = 0
                use_hwaccel = ff_settings.get_use_hardware_encoder()
                duration = video_record.duration_seconds or 0.0

                # Evict ML models BEFORE computing the budget so the budget
                # sees the RAM freed by Whisper/TTS, enabling single-pass mode
                # and normal process priority on memory-constrained machines.
                # On machines with >= 5 GB free the models stay warm.
                _, pre_avail = get_memory_gb()
                if pre_avail < 5.0:
                    tts_registry.evict_all()
                    unload_whisper_models()
                    gc.collect()
                    logger.info(
                        f"[Pipeline {video_id}] Freed ML models before compositing "
                        f"(pre_available={pre_avail:.1f}GB)"
                    )
                else:
                    logger.info(
                        f"[Pipeline {video_id}] Keeping ML models in memory "
                        f"(pre_available={pre_avail:.1f}GB)"
                    )

                budget = compute_resource_budget(
                    duration,
                    ffmpeg_threads_override=threads_override,
                )

                if needs_segmentation(duration, budget):
                    total_segs = segment_count(duration, budget)
                    compose_msg = f"Rendering segment 1/{total_segs}"
                else:
                    compose_msg = "Rendering video"
                self._update_progress(
                    video_record,
                    "compositing",
                    0,
                    progress_callback,
                    status_message=compose_msg,
                )

                def ff_callback(
                    percent: int,
                    step: str,
                    message: Optional[str] = None,
                ) -> None:
                    self._update_progress(
                        video_record, "compositing", percent,
                        progress_callback, throttle_sec=1.5,
                        force=(percent >= 99),
                        status_message=message,
                    )

                # Thumbnail only needs story metadata — start it concurrently
                # with the (long) compose step to overlap CPU/disk work.
                self.check_cancelled(video_record)
                _thumbnail_task: asyncio.Task = asyncio.create_task(
                    asyncio.to_thread(
                        self.thumbnail_gen.generate,
                        story.title,
                        story.subreddit,
                        Path(video_record.thumbnail_path),
                        score=story.score,
                    ),
                    name=f"thumbnail_{video_id}",
                )

                try:
                    final_duration = await self.composer.compose(
                        bg_video,
                        str(audio_path),
                        str(subtitle_path) if Path(subtitle_path).exists() else None,
                        str(output_folder / "video.mp4"),
                        video_format=video_format,
                        audio_duration=duration,
                        progress_callback=ff_callback,
                        encode_params=encode_params,
                        use_hwaccel=use_hwaccel,
                        resource_budget=budget,
                    )
                except BaseException:
                    _thumbnail_task.cancel()
                    raise

                logger.info(
                    f"[Pipeline {video_id}] Compositing done in "
                    f"{time.monotonic()-compose_t:.1f}s"
                )

                video_record.duration_seconds = final_duration
                video_record.status = VideoStatus.COMPOSITING_DONE.value
                self.db.commit()
                self._save_checkpoint(
                    video_record, "compositing_done",
                    {**checkpoint, "video_path": str(output_folder / "video.mp4")},
                )
            else:
                logger.info(f"[Pipeline {video_id}] Compositing skipped (checkpoint)")
                _thumbnail_task = None  # type: ignore[assignment]

            self._update_progress(
                video_record, "compositing_done", 0, progress_callback
            )

            # ── Thumbnail ──────────────────────────────────────────────
            self.check_cancelled(video_record)
            self._update_progress(
                video_record, "generating_thumbnail", 0, progress_callback
            )
            if _thumbnail_task is not None:
                # Already running concurrently — just collect the result.
                await _thumbnail_task
            else:
                await asyncio.to_thread(
                    self.thumbnail_gen.generate,
                    story.title,
                    story.subreddit,
                    Path(video_record.thumbnail_path),
                    score=story.score,
                )
            self._update_progress(
                video_record, "generating_thumbnail", 100, progress_callback
            )

            # ── Done ───────────────────────────────────────────────────
            video_path = Path(video_record.video_path or "")
            if not video_path.is_file() or video_path.stat().st_size < 1024:
                raise VideoPipelineError(
                    "Video file is missing or incomplete after generation. "
                    "Please retry or resume generation."
                )

            video_record.status = VideoStatus.DONE.value
            video_record.progress_percent = 100
            video_record.current_step = "done"
            video_record.completed_at = datetime.now(timezone.utc)
            try:
                video_record.file_size_bytes = Path(video_record.video_path).stat().st_size
            except (OSError, FileNotFoundError):
                video_record.file_size_bytes = None

            story.status = StoryStatus.VIDEO_DONE.value
            self.db.commit()
            progress_push.push_progress(
                video_id,
                _build_progress_payload(video_record, "done"),
            )
            logger.info(
                f"[Pipeline {video_id}] Complete in "
                f"{time.monotonic()-t_start:.1f}s total"
            )

            cleanup_temp(video_id)

            try:
                await notification_queue.broadcast("video_complete", {
                    "video_id": video_id, "story_id": story.id,
                    "status": "done", "title": story.title,
                })
            except Exception as notif_err:
                logger.warning(
                    f"[Pipeline {video_id}] Notification error: {notif_err}"
                )

            return video_record

        except PipelineCancelledError:
            logger.info(f"[Pipeline {video_id}] Cancelled")
            still_exists = self.db.query(GeneratedVideo).filter(
                GeneratedVideo.id == video_id
            ).first()
            if still_exists:
                video_record.status = VideoStatus.CANCELLED.value
                video_record.cancelled_at = datetime.now(timezone.utc)
                story.status = StoryStatus.VIDEO_CANCELLED.value
                self.db.commit()
                progress_push.push_progress(
                    video_id, _build_progress_payload(video_record, "cancelled")
                )
                cleanup_temp(video_id)
                try:
                    await notification_queue.broadcast("video_cancelled", {
                        "video_id": video_id,
                        "story_id": story.id,
                        "status": "cancelled",
                    })
                except Exception:
                    pass
            raise

        except PipelinePausedError:
            logger.info(f"[Pipeline {video_id}] Paused")
            video_record.status = VideoStatus.PAUSED.value
            video_record.is_paused = True
            video_record.paused_at = datetime.now(timezone.utc)
            story.status = StoryStatus.VIDEO_PAUSED.value
            self.db.commit()
            progress_push.push_progress(
                video_id, _build_progress_payload(video_record, "paused")
            )
            raise

        except (TTSProviderError, FFmpegComposerError, OSError) as exc:
            logger.error(
                f"[Pipeline {video_id}] Domain error: {exc}", exc_info=True
            )
            self._record_error(video_record, exc, video_record.current_step)
            story.status = StoryStatus.VIDEO_FAILED.value
            self.db.commit()
            cleanup_temp(video_id)
            try:
                await notification_queue.broadcast("video_failed", {
                    "video_id": video_id, "story_id": story.id,
                    "status": "failed", "error": str(exc),
                    "step": video_record.current_step,
                })
            except Exception:
                pass
            raise VideoPipelineError(
                f"Pipeline failed at {video_record.current_step}: {exc}"
            )

        except Exception as exc:
            logger.error(
                f"[Pipeline {video_id}] Unexpected error: {exc}", exc_info=True
            )
            self._record_error(video_record, exc, video_record.current_step)
            story.status = StoryStatus.VIDEO_FAILED.value
            self.db.commit()
            cleanup_temp(video_id)
            try:
                await notification_queue.broadcast("video_failed", {
                    "video_id": video_id, "story_id": story.id,
                    "status": "failed", "error": str(exc),
                    "step": video_record.current_step,
                })
            except Exception:
                pass
            raise VideoPipelineError(
                f"Pipeline failed at {video_record.current_step}: {exc}"
            )

    # ------------------------------------------------------------------
    # Legacy REST progress endpoint helper
    # ------------------------------------------------------------------

    def get_progress(self, video_id: int) -> dict:
        video = (
            self.db.query(GeneratedVideo)
            .filter(GeneratedVideo.id == video_id)
            .first()
        )
        if not video:
            raise VideoPipelineError(f"Video {video_id} not found")
        return _build_progress_payload(video, video.current_step or "")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_whisper_model_size(db: Session) -> str:
    try:
        from core.settings_manager import SettingsManager
        mgr = SettingsManager(db)
        size = mgr.get("whisper_model_size")
        return size if size in ("tiny", "base", "small", "medium", "large") else "base"
    except Exception:
        return "base"


def _build_progress_payload(
    video: GeneratedVideo,
    step: str,
    status_message: Optional[str] = None,
) -> dict:
    step = step or ""
    message = (
        status_message
        or video.status_message
        or _STEP_MESSAGES.get(step, step)
    )
    return {
        "video_id": video.id,
        "status": video.status,
        "progress_percent": video.progress_percent,
        "current_step": step,
        "status_message": message,
        "step_progress": video.step_progress,
        "error_message": video.error_message,
        "error_type": video.error_type,
        "error_step": video.error_step,
        "queue_position": video.queue_position,
        "is_paused": video.is_paused,
        "retry_count": video.retry_count,
        "thumbnail_path": video.thumbnail_path,
        "video_path": video.video_path,
    }
