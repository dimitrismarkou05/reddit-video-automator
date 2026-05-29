import asyncio
import json
import logging
import re
import shutil
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

logger = logging.getLogger(__name__)


class VideoPipelineError(Exception):
    pass


class PipelineCancelledError(Exception):
    pass


class PipelinePausedError(Exception):
    pass


# FIXED: Smoother step progress mapping - monotonically increasing
# Each step builds on the previous, no backtracking
STEP_PROGRESS = {
    "queued": 0,
    "preparing": 2,
    "downloading_model": 5,
    "initializing_pipeline": 5,
    "generating_script": 5,
    "tts": 10,
    "tts_synthesizing": 15,
    "tts_done": 30,
    "transcribing": 35,
    "transcribe_done": 45,
    "generating_subtitles": 48,
    "subtitles_done": 55,
    "selecting_background": 58,
    "compositing": 60,
    "ffmpeg_processing": 70,
    "compositing_done": 85,
    "thumbnail": 90,
    "generating_thumbnail": 92,
    "uploading": 95,
    "cleanup": 98,
    "done": 100,
    "failed": 0,
}


class VideoPipeline:
    def __init__(self, db: Session, ffmpeg_path: str = "ffmpeg"):
        self.db = db
        self.ffmpeg_path = ffmpeg_path
        self.composer = FFmpegComposer(ffmpeg_path)
        self.subtitle_gen = SubtitleGenerator(model_size="base")
        self.thumbnail_gen = ThumbnailGenerator()
        self._cancelled = False
        self._paused = False
        self._progress_callback: Optional[Callable[[int, str], None]] = None

    def _update_progress(
        self,
        video_record: GeneratedVideo,
        step: str,
        step_progress: int = 0,
        callback: Optional[Callable[[int, str], None]] = None,
    ) -> None:
        """Update video progress in DB and call optional callback.
        
        FIX: Ensure progress never decreases (monotonic).
        """
        try:
            base_percent = STEP_PROGRESS.get(step, 0)
            new_percent = min(base_percent + step_progress, 99)
            
            # CRITICAL FIX: Never decrease progress
            if video_record.progress_percent is not None and new_percent < video_record.progress_percent:
                new_percent = video_record.progress_percent
            
            video_record.progress_percent = new_percent
            video_record.current_step = step
            video_record.step_progress = step_progress
            self.db.commit()
            logger.debug(f"[Pipeline {video_record.id}] Progress: {step} {new_percent}%")
            if callback:
                try:
                    callback(new_percent, step)
                except Exception as cb_err:
                    logger.warning(f"[Pipeline {video_record.id}] Progress callback error: {cb_err}")
        except Exception as db_err:
            logger.error(f"[Pipeline {video_record.id}] DB progress update error: {db_err}")

    def _save_checkpoint(
        self,
        video_record: GeneratedVideo,
        step: str,
        temp_data: dict,
    ) -> None:
        try:
            video_record.current_step = step
            video_record.temp_files_json = temp_data
            self.db.commit()
            logger.debug(f"[Pipeline {video_record.id}] Checkpoint saved: {step}")
        except Exception as e:
            logger.error(f"[Pipeline {video_record.id}] Checkpoint save error: {e}")

    def _load_checkpoint(self, video_record: GeneratedVideo) -> dict:
        checkpoint = video_record.temp_files_json or {}
        logger.debug(f"[Pipeline {video_record.id}] Loaded checkpoint: {checkpoint.get('step', 'none')}")
        return checkpoint

    def _build_narrative_text(self, story: Story, include_updates: bool) -> str:
        linker = UpdateLinker(self.db)
        if include_updates:
            return linker.get_full_narrative(story.id, include_inline_updates=True)
        else:
            return f"{story.title}. {story.body or ''}"

    def _generate_hashtags(self, text: str) -> List[str]:
        words = text.lower().split()
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                     "being", "have", "has", "had", "do", "does", "did", "will",
                     "would", "could", "should", "may", "might", "must", "shall",
                     "can", "need", "dare", "ought", "used", "to", "of", "in", "for",
                     "on", "with", "at", "by", "from", "as", "into", "through", "during",
                     "before", "after", "above", "below", "between", "under", "and",
                     "but", "or", "yet", "so", "if", "because", "although", "though",
                     "while", "where", "when", "that", "which", "who", "whom", "whose",
                     "what", "this", "these", "those", "i", "you", "he", "she", "it",
                     "we", "they", "me", "him", "her", "us", "them", "my", "your",
                     "his", "her", "its", "our", "their", "mine", "yours", "hers",
                     "ours", "theirs", "myself", "yourself", "himself", "herself",
                     "itself", "ourselves", "yourselves", "themselves", "am", "are",
                     "is", "was", "were", "be", "been", "being", "have", "has", "had",
                     "do", "does", "did", "will", "would", "shall", "should", "may",
                     "might", "can", "could", "must", "ought", "need", "dare", "used",
                     "i'm", "it's", "that's", "there's", "here's", "what's", "who's",
                     "where's", "when's", "why's", "how's", "don't", "doesn't", "didn't",
                     "won't", "wouldn't", "shan't", "shouldn't", "can't", "cannot",
                     "couldn't", "mustn't", "let's", "that's", "who's", "what's",
                     "here's", "there's", "when's", "where's", "why's", "how's"}

        freq = {}
        for word in words:
            word = re.sub(r'[^\\w]', '', word)
            if len(word) > 3 and word not in stop_words:
                freq[word] = freq.get(word, 0) + 1

        top = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:5]
        hashtags = [f"#{word}" for word, _ in top]
        hashtags.extend(["#Reddit", "#StoryTime", "#RedditStories"])

        return hashtags[:8]

    def check_cancelled(self, video_record: GeneratedVideo) -> None:
        if self._cancelled:
            raise PipelineCancelledError("Video generation was cancelled")
        try:
            self.db.refresh(video_record)
        except Exception as e:
            logger.warning(f"[Pipeline {video_record.id}] DB refresh error during cancel check: {e}")
        if video_record.status == VideoStatus.CANCELLED.value:
            raise PipelineCancelledError("Video generation was cancelled")
        if video_record.status == VideoStatus.PAUSED.value:
            self._paused = True
            raise PipelinePausedError("Video generation was paused")

    def cancel(self) -> None:
        self._cancelled = True
        self.composer.cancel()
        logger.info("[Pipeline] Cancel signal received")

    def pause(self) -> None:
        self._paused = True
        self.composer.cancel()
        logger.info("[Pipeline] Pause signal received")

    def resume(self) -> None:
        self._paused = False
        logger.info("[Pipeline] Resume signal received")

    def _record_error(
        self,
        video_record: GeneratedVideo,
        error: Exception,
        step: str,
    ) -> None:
        raw = str(error)
        if "api key" in raw.lower() or "not configured" in raw.lower():
            friendly = "TTS model not installed. Check Settings."
        elif "TTS" in type(error).__name__ or "tts" in raw.lower():
            friendly = "Text-to-speech failed. Install a TTS model in Settings."
        elif "FFmpeg" in type(error).__name__ or "ffmpeg" in raw.lower():
            friendly = "Video rendering failed. Check FFmpeg installation."
        elif "duration" in raw.lower() or "Could not determine duration" in raw:
            friendly = "Audio processing failed. The TTS output may be corrupted. Try again."
        else:
            friendly = f"Generation failed: {raw}"

        video_record.status = VideoStatus.FAILED.value
        video_record.error_message = friendly
        video_record.error_type = type(error).__name__
        video_record.error_step = step
        video_record.error_traceback = traceback.format_exc()
        video_record.current_step = step
        try:
            self.db.commit()
            logger.error(f"[Pipeline {video_record.id}] Error recorded: {friendly} at {step}")
        except Exception as e:
            logger.error(f"[Pipeline {video_record.id}] DB error commit during error recording: {e}")

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
        """Async video generation pipeline."""
        self._progress_callback = progress_callback
        self._cancelled = False
        self._paused = False

        story = self.db.query(Story).filter(Story.id == video_record.story_id).first()
        if not story:
            raise VideoPipelineError(f"Story {video_record.story_id} not found")

        video_id = video_record.id
        output_folder = get_output_folder(story.id, story.title)
        temp_folder = get_temp_folder(video_id)

        # Ensure output paths are set
        if not video_record.video_path:
            video_record.video_path = str(output_folder / "video.mp4")
        if not video_record.thumbnail_path:
            video_record.thumbnail_path = str(output_folder / "thumbnail.jpg")
        self.db.commit()

        checkpoint = self._load_checkpoint(video_record)

        logger.info(f"[Pipeline {video_id}] Starting generation for story {story.id}")
        logger.info(f"[Pipeline {video_id}] Checkpoint step: {checkpoint.get('step', 'queued')}")
        logger.info(f"[Pipeline {video_id}] Output folder: {output_folder}")
        logger.info(f"[Pipeline {video_id}] Temp folder: {temp_folder}")

        try:
            # Step: preparing
            if checkpoint.get("step", "queued") in ("queued", "failed"):
                self.check_cancelled(video_record)
                self._update_progress(video_record, "preparing", 0, progress_callback)
                narrative = self._build_narrative_text(story, include_updates)

                hashtags = []
                if generate_hashtags:
                    hashtags = self._generate_hashtags(narrative)
                    current_style = video_record.subtitle_style or {}
                    if isinstance(current_style, dict):
                        current_style["hashtags"] = hashtags
                    else:
                        current_style = {"hashtags": hashtags}
                    video_record.subtitle_style = current_style

                video_record.background_source = background_source
                self.db.commit()
                self._save_checkpoint(video_record, "preparing", {})
                logger.info(f"[Pipeline {video_id}] Narrative prepared, length={len(narrative)}")
            else:
                narrative = self._build_narrative_text(story, include_updates)

            # Step: TTS
            audio_path = temp_folder / "narration.wav"
            if checkpoint.get("step", "preparing") in ("queued", "preparing", "failed"):
                self.check_cancelled(video_record)
                self._update_progress(video_record, "tts", 0, progress_callback)

                tts_engine = TTSEngine(self.db)
                logger.info(f"[Pipeline {video_id}] Starting TTS synthesis")

                # FIX: Properly mapped progress callbacks to prevent 99% jump
                self._update_progress(video_record, "downloading_model", 0, progress_callback)

                try:
                    tts_progress = {"model_loaded": False}

                    def tts_load_callback(percent: int, step: str) -> None:
                        """Map TTS internal 0-100 to pipeline's 5-15% range."""
                        if not tts_progress["model_loaded"]:
                            # downloading_model base = 5, max step_progress = 10 → caps at 15%
                            mapped = min(int(percent * 0.10), 10)
                            self._update_progress(
                                video_record, "downloading_model", mapped, progress_callback
                            )
                            if percent >= 100:
                                tts_progress["model_loaded"] = True
                                self._update_progress(
                                    video_record, "tts_synthesizing", 0, progress_callback
                                )

                    try:
                        audio_duration = await asyncio.to_thread(
                            tts_engine.synthesize,
                            narrative, voice_id, audio_path,
                            progress_callback=tts_load_callback,
                        )
                    except TypeError:
                        # Fallback: synthesize doesn't accept progress_callback
                        self._update_progress(video_record, "downloading_model", 5, progress_callback)
                        self._update_progress(video_record, "tts_synthesizing", 0, progress_callback)
                        audio_duration = await asyncio.to_thread(
                            tts_engine.synthesize,
                            narrative, voice_id, audio_path,
                        )

                    logger.info(f"[Pipeline {video_id}] TTS synthesis complete, duration={audio_duration:.1f}s")
                except Exception as tts_err:
                    logger.error(f"[Pipeline {video_id}] TTS synthesis failed: {tts_err}", exc_info=True)
                    raise TTSProviderError(f"TTS failed: {tts_err}")

                video_record.audio_path = str(audio_path)
                video_record.duration_seconds = audio_duration
                video_record.tts_audio_path = str(audio_path)
                video_record.status = VideoStatus.TTS_DONE.value
                self.db.commit()
                self._save_checkpoint(video_record, "tts_done", {
                    "audio_path": str(audio_path),
                })
                logger.info(f"[Pipeline {video_id}] TTS complete, duration={audio_duration:.1f}s")
            else:
                audio_path = Path(checkpoint.get("audio_path", str(audio_path)))
                logger.info(f"[Pipeline {video_id}] TTS skipped (checkpoint), using {audio_path}")

            self._update_progress(video_record, "tts_done", 0, progress_callback)

            # Step: Transcribe
            whisper_result = None
            if checkpoint.get("step", "tts_done") in ("queued", "preparing", "tts_done", "failed"):
                self.check_cancelled(video_record)
                self._update_progress(video_record, "transcribing", 0, progress_callback)
                
                # Explicitly ensure FFmpeg is in PATH for Whisper
                if not ensure_ffmpeg_in_path():
                    raise VideoPipelineError("FFmpeg not found. Please install FFmpeg in Settings.")
                
                logger.info(f"[Pipeline {video_id}] Starting transcription")
                whisper_result = await asyncio.to_thread(
                    self.subtitle_gen.transcribe, str(audio_path)
                )

                logger.info(f"[Pipeline {video_id}] Starting transcription")
                whisper_result = await asyncio.to_thread(
                    self.subtitle_gen.transcribe, str(audio_path)
                )

                video_record.whisper_result_json = whisper_result
                video_record.status = VideoStatus.TRANSCRIBE_DONE.value
                self.db.commit()
                self._save_checkpoint(video_record, "transcribe_done", {
                    **checkpoint,
                    "whisper_result": True,
                })
                logger.info(f"[Pipeline {video_id}] Transcription complete")
            else:
                whisper_result = video_record.whisper_result_json
                logger.info(f"[Pipeline {video_id}] Transcription skipped (checkpoint)")

            self._update_progress(video_record, "transcribe_done", 0, progress_callback)

            # Step: Subtitles
            subtitle_path = temp_folder / "subtitles.ass"
            if checkpoint.get("step", "transcribe_done") in (
                "queued", "preparing", "tts_done", "transcribe_done", "failed"
            ):
                self.check_cancelled(video_record)
                self._update_progress(video_record, "generating_subtitles", 0, progress_callback)

                if whisper_result is None:
                    logger.warning(f"[Pipeline {video_id}] No whisper result, re-transcribing")
                    whisper_result = await asyncio.to_thread(
                        self.subtitle_gen.transcribe, str(audio_path)
                    )

                dims = {"shorts": (1080, 1920), "normal": (1920, 1080)}
                w, h = dims.get(video_format, (1080, 1920))
                logger.info(f"[Pipeline {video_id}] Generating subtitles ASS, dims={w}x{h}")
                await asyncio.to_thread(
                    self.subtitle_gen.generate_ass,
                    whisper_result,
                    subtitle_path,
                    subtitle_style or SubtitleStyle(),
                    video_width=w,
                    video_height=h,
                )
                video_record.subtitle_path = str(subtitle_path)
                video_record.subtitle_ass_path = str(subtitle_path)
                video_record.status = VideoStatus.SUBTITLES_DONE.value
                self.db.commit()
                self._save_checkpoint(video_record, "subtitles_done", {
                    **checkpoint,
                    "subtitle_path": str(subtitle_path),
                })
                logger.info(f"[Pipeline {video_id}] Subtitles generated")
            else:
                subtitle_path = Path(checkpoint.get("subtitle_path", str(subtitle_path)))
                logger.info(f"[Pipeline {video_id}] Subtitles skipped (checkpoint), using {subtitle_path}")

            self._update_progress(video_record, "subtitles_done", 0, progress_callback)

            # Step: Select background
            if checkpoint.get("step", "subtitles_done") in (
                "queued", "preparing", "tts_done", "transcribe_done", "subtitles_done", "failed"
            ):
                self.check_cancelled(video_record)
                self._update_progress(video_record, "selecting_background", 0, progress_callback)
                logger.info(f"[Pipeline {video_id}] Selecting background from: {background_source}")
                bg_video = await asyncio.to_thread(select_background_video, background_source)
                video_record.selected_background_video = bg_video
                self.db.commit()
                self._save_checkpoint(video_record, "selecting_background", {
                    **checkpoint,
                    "bg_video": bg_video,
                })
                logger.info(f"[Pipeline {video_id}] Background selected: {bg_video}")
            else:
                bg_video = checkpoint.get("bg_video") or video_record.selected_background_video
                if not bg_video:
                    logger.info(f"[Pipeline {video_id}] No background in checkpoint, selecting fresh")
                    bg_video = await asyncio.to_thread(select_background_video, background_source)
                else:
                    logger.info(f"[Pipeline {video_id}] Background skipped (checkpoint), using {bg_video}")

            # Step: Compositing
            if checkpoint.get("step", "selecting_background") in (
                "queued", "preparing", "tts_done", "transcribe_done",
                "subtitles_done", "selecting_background", "failed"
            ):
                self.check_cancelled(video_record)
                self._update_progress(video_record, "compositing", 0, progress_callback)
                logger.info(f"[Pipeline {video_id}] Starting FFmpeg compositing")

                def ff_callback(percent, step):
                    # Map FFmpeg's 0-100 to our compositing range (60-85)
                    mapped = 60 + int(percent * 0.25)
                    # Ensure we don't exceed compositing_done base
                    mapped = min(mapped, 84)
                    self._update_progress(video_record, "compositing", mapped - 60, progress_callback)

                final_duration = await self.composer.compose(
                    bg_video,
                    str(audio_path),
                    str(subtitle_path) if Path(subtitle_path).exists() else None,
                    str(output_folder / "video.mp4"),
                    video_format=video_format,
                    audio_duration=video_record.duration_seconds,   # <-- pass stored duration
                    progress_callback=ff_callback,
                )
                video_record.duration_seconds = final_duration
                video_record.status = VideoStatus.COMPOSITING_DONE.value
                self.db.commit()
                self._save_checkpoint(video_record, "compositing_done", {
                    **checkpoint,
                    "video_path": str(output_folder / "video.mp4"),
                })
                logger.info(f"[Pipeline {video_id}] Compositing complete, duration={final_duration:.1f}s")
            else:
                logger.info(f"[Pipeline {video_id}] Compositing skipped (checkpoint)")

            self._update_progress(video_record, "compositing_done", 0, progress_callback)

            # Step: Thumbnail
            self.check_cancelled(video_record)
            self._update_progress(video_record, "generating_thumbnail", 0, progress_callback)
            logger.info(f"[Pipeline {video_id}] Generating thumbnail")
            await asyncio.to_thread(
                self.thumbnail_gen.generate,
                story.title,
                story.subreddit,
                Path(video_record.thumbnail_path),
                score=story.score,
            )
            logger.info(f"[Pipeline {video_id}] Thumbnail generated")

            # Step: Done
            video_record.status = VideoStatus.DONE.value
            video_record.progress_percent = 100
            video_record.current_step = "done"
            video_record.completed_at = datetime.now(timezone.utc)
            try:
                video_record.file_size_bytes = Path(video_record.video_path).stat().st_size
            except (OSError, FileNotFoundError):
                video_record.file_size_bytes = None
                logger.warning(f"[Pipeline {video_id}] Could not get file size")

            story.status = StoryStatus.VIDEO_DONE.value
            self.db.commit()
            logger.info(f"[Pipeline {video_id}] Final DB commit, status=DONE")

            # Cleanup
            cleanup_temp(video_id)
            logger.info(f"[Pipeline {video_id}] Temp files cleaned up")

            self._update_progress(video_record, "done", 0, progress_callback)

            logger.info(f"[Pipeline {video_id}] Generation complete!")

            # Broadcast completion notification
            try:
                await notification_queue.broadcast("video_complete", {
                    "video_id": video_id,
                    "story_id": story.id,
                    "status": "done",
                    "title": story.title,
                })
                logger.info(f"[Pipeline {video_id}] Completion notification broadcast")
            except Exception as notif_err:
                logger.warning(f"[Pipeline {video_id}] Notification broadcast error: {notif_err}")

            return video_record

        except PipelineCancelledError:
            logger.info(f"[Pipeline {video_id}] Handling cancellation")
            video_record.status = VideoStatus.CANCELLED.value
            video_record.cancelled_at = datetime.now(timezone.utc)
            story.status = StoryStatus.VIDEO_CANCELLED.value
            self.db.commit()
            cleanup_temp(video_id)
            logger.info(f"[Pipeline {video_id}] Generation cancelled, cleanup complete")

            # Broadcast cancel notification
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
            logger.info(f"[Pipeline {video_id}] Handling pause")
            video_record.status = VideoStatus.PAUSED.value
            video_record.is_paused = True
            video_record.paused_at = datetime.now(timezone.utc)
            story.status = StoryStatus.VIDEO_PAUSED.value
            self.db.commit()
            logger.info(f"[Pipeline {video_id}] Generation paused")
            raise

        except (TTSProviderError, FFmpegComposerError, OSError) as exc:
            logger.error(f"[Pipeline {video_id}] Pipeline domain error: {exc}", exc_info=True)
            self._record_error(video_record, exc, video_record.current_step)
            story.status = StoryStatus.VIDEO_FAILED.value
            self.db.commit()
            cleanup_temp(video_id)

            # Broadcast failure notification
            try:
                await notification_queue.broadcast("video_failed", {
                    "video_id": video_id,
                    "story_id": story.id,
                    "status": "failed",
                    "error": str(exc),
                    "step": video_record.current_step,
                })
            except Exception:
                pass
            raise VideoPipelineError(f"Video generation failed at {video_record.current_step}: {exc}")

        except Exception as exc:
            logger.error(f"[Pipeline {video_id}] Unexpected error: {exc}", exc_info=True)
            self._record_error(video_record, exc, video_record.current_step)
            story.status = StoryStatus.VIDEO_FAILED.value
            self.db.commit()
            cleanup_temp(video_id)

            # Broadcast failure notification
            try:
                await notification_queue.broadcast("video_failed", {
                    "video_id": video_id,
                    "story_id": story.id,
                    "status": "failed",
                    "error": str(exc),
                    "step": video_record.current_step,
                })
            except Exception:
                pass
            raise VideoPipelineError(f"Video generation failed at {video_record.current_step}: {exc}")

    def get_progress(self, video_id: int) -> dict:
        video = self.db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
        if not video:
            raise VideoPipelineError(f"Video {video_id} not found")

        return {
            "video_id": video.id,
            "status": video.status,
            "progress_percent": video.progress_percent,
            "current_step": video.current_step,
            "step_progress": video.step_progress,
            "error_message": video.error_message,
            "error_type": video.error_type,
            "error_step": video.error_step,
            "queue_position": video.queue_position,
            "is_paused": video.is_paused,
        }