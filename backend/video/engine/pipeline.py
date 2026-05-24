"""End-to-end video generation pipeline with checkpointing, resume, and retry."""

import asyncio
import json
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


class VideoPipelineError(Exception):
    pass


class PipelineCancelledError(Exception):
    pass


class PipelinePausedError(Exception):
    pass


STEP_PROGRESS = {
    "queued": 0,
    "preparing": 5,
    "tts": 10,
    "tts_done": 30,
    "transcribe_done": 45,
    "subtitles_done": 55,
    "selecting_background": 55,
    "compositing": 60,
    "compositing_done": 92,
    "thumbnail": 92,
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

    def _update_progress(
        self,
        video_record: GeneratedVideo,
        step: str,
        step_progress: int = 0,
        callback: Optional[Callable[[int, str], None]] = None,
    ) -> None:
        base_percent = STEP_PROGRESS.get(step, 0)
        video_record.progress_percent = min(base_percent + step_progress, 99)
        video_record.current_step = step
        video_record.step_progress = step_progress
        self.db.commit()
        if callback:
            callback(video_record.progress_percent, step)

    def _save_checkpoint(
        self,
        video_record: GeneratedVideo,
        step: str,
        temp_data: dict,
    ) -> None:
        video_record.current_step = step
        video_record.temp_files_json = temp_data
        self.db.commit()

    def _load_checkpoint(self, video_record: GeneratedVideo) -> dict:
        return video_record.temp_files_json or {}

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
                     "i\'m", "it\'s", "that\'s", "there\'s", "here\'s", "what\'s", "who\'s",
                     "where\'s", "when\'s", "why\'s", "how\'s", "don\'t", "doesn\'t", "didn\'t",
                     "won\'t", "wouldn\'t", "shan\'t", "shouldn\'t", "can\'t", "cannot",
                     "couldn\'t", "mustn\'t", "let\'s", "that\'s", "who\'s", "what\'s",
                     "here\'s", "there\'s", "when\'s", "where\'s", "why\'s", "how\'s"}

        freq = {}
        for word in words:
            word = re.sub(r'[^\w]', '', word)
            if len(word) > 3 and word not in stop_words:
                freq[word] = freq.get(word, 0) + 1

        top = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:5]
        hashtags = [f"#{word}" for word, _ in top]
        hashtags.extend(["#Reddit", "#StoryTime", "#RedditStories"])

        return hashtags[:8]

    def check_cancelled(self, video_record: GeneratedVideo) -> None:
        if self._cancelled:
            raise PipelineCancelledError("Video generation was cancelled")
        self.db.refresh(video_record)
        if video_record.status == VideoStatus.CANCELLED.value:
            raise PipelineCancelledError("Video generation was cancelled")
        if video_record.status == VideoStatus.PAUSED.value:
            self._paused = True
            raise PipelinePausedError("Video generation was paused")

    def cancel(self) -> None:
        self._cancelled = True
        self.composer.cancel()

    def pause(self) -> None:
        self._paused = True
        self.composer.cancel()

    def resume(self) -> None:
        self._paused = False

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
        else:
            friendly = f"Generation failed: {raw}"

        video_record.status = VideoStatus.FAILED.value
        video_record.error_message = friendly
        video_record.error_type = type(error).__name__
        video_record.error_step = step
        video_record.error_traceback = traceback.format_exc()
        video_record.current_step = step
        self.db.commit()

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
        story = self.db.query(Story).filter(Story.id == video_record.story_id).first()
        if not story:
            raise VideoPipelineError(f"Story {video_record.story_id} not found")

        video_id = video_record.id
        output_folder = get_output_folder(story.id, story.title)
        temp_folder = get_temp_folder(video_id)

        video_record.video_path = str(output_folder / "video.mp4")
        video_record.thumbnail_path = str(output_folder / "thumbnail.jpg")
        self.db.commit()

        checkpoint = self._load_checkpoint(video_record)

        try:
            if checkpoint.get("step", "queued") in ("queued", "failed"):
                self.check_cancelled(video_record)
                self._update_progress(video_record, "preparing", 0, progress_callback)
                narrative = self._build_narrative_text(story, include_updates)

                hashtags = []
                if generate_hashtags:
                    hashtags = self._generate_hashtags(narrative)
                    video_record.subtitle_style = {
                        **(video_record.subtitle_style or {}),
                        "hashtags": hashtags,
                    }

                video_record.background_source = background_source
                self.db.commit()
                self._save_checkpoint(video_record, "preparing", {})
            else:
                narrative = self._build_narrative_text(story, include_updates)

            audio_path = temp_folder / "narration.wav"
            if checkpoint.get("step", "preparing") in ("queued", "preparing", "failed"):
                self.check_cancelled(video_record)
                self._update_progress(video_record, "tts", 0, progress_callback)

                tts_engine = TTSEngine(self.db)
                audio_duration = await asyncio.to_thread(
                    tts_engine.synthesize,
                    narrative, voice_id, audio_path,
                )

                video_record.audio_path = str(audio_path)
                video_record.duration_seconds = audio_duration
                video_record.tts_audio_path = str(audio_path)
                video_record.status = VideoStatus.TTS_DONE.value
                self.db.commit()
                self._save_checkpoint(video_record, "tts_done", {
                    "audio_path": str(audio_path),
                })
            else:
                audio_path = Path(checkpoint.get("audio_path", str(audio_path)))

            self._update_progress(video_record, "tts_done", 0, progress_callback)

            whisper_result = None
            if checkpoint.get("step", "tts_done") in ("queued", "preparing", "tts_done", "failed"):
                self.check_cancelled(video_record)
                self._update_progress(video_record, "transcribe_done", 0, progress_callback)

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
            else:
                whisper_result = video_record.whisper_result_json

            self._update_progress(video_record, "transcribe_done", 0, progress_callback)

            subtitle_path = temp_folder / "subtitles.ass"
            if checkpoint.get("step", "transcribe_done") in (
                "queued", "preparing", "tts_done", "transcribe_done", "failed"
            ):
                self.check_cancelled(video_record)
                self._update_progress(video_record, "subtitles_done", 0, progress_callback)

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
            else:
                subtitle_path = Path(checkpoint.get("subtitle_path", str(subtitle_path)))

            self._update_progress(video_record, "subtitles_done", 0, progress_callback)

            if checkpoint.get("step", "subtitles_done") in (
                "queued", "preparing", "tts_done", "transcribe_done", "subtitles_done", "failed"
            ):
                self.check_cancelled(video_record)
                self._update_progress(video_record, "selecting_background", 0, progress_callback)
                bg_video = await asyncio.to_thread(select_background_video, background_source)
                video_record.selected_background_video = bg_video
                self.db.commit()
                self._save_checkpoint(video_record, "selecting_background", {
                    **checkpoint,
                    "bg_video": bg_video,
                })
            else:
                bg_video = checkpoint.get("bg_video") or video_record.selected_background_video
                if not bg_video:
                    bg_video = await asyncio.to_thread(select_background_video, background_source)

            if checkpoint.get("step", "selecting_background") in (
                "queued", "preparing", "tts_done", "transcribe_done",
                "subtitles_done", "selecting_background", "failed"
            ):
                self.check_cancelled(video_record)
                self._update_progress(video_record, "compositing", 0, progress_callback)

                def ff_callback(percent, step):
                    mapped = 60 + int(percent * 0.3)
                    self._update_progress(video_record, "compositing", mapped - 60, progress_callback)

                final_duration = await self.composer.compose(
                    bg_video,
                    str(audio_path),
                    str(subtitle_path) if Path(subtitle_path).exists() else None,
                    str(output_folder / "video.mp4"),
                    video_format=video_format,
                    progress_callback=ff_callback,
                )
                video_record.duration_seconds = final_duration
                video_record.status = VideoStatus.COMPOSITING_DONE.value
                self.db.commit()
                self._save_checkpoint(video_record, "compositing_done", {
                    **checkpoint,
                    "video_path": str(output_folder / "video.mp4"),
                })

            self._update_progress(video_record, "compositing_done", 0, progress_callback)

            self.check_cancelled(video_record)
            self._update_progress(video_record, "thumbnail", 0, progress_callback)
            await asyncio.to_thread(
                self.thumbnail_gen.generate,
                story.title,
                story.subreddit,
                Path(video_record.thumbnail_path),
                score=story.score,
            )

            video_record.status = VideoStatus.DONE.value
            video_record.progress_percent = 100
            video_record.current_step = "done"
            video_record.completed_at = datetime.now(timezone.utc)
            video_record.file_size_bytes = Path(video_record.video_path).stat().st_size

            story.status = StoryStatus.VIDEO_DONE.value

            self.db.commit()

            cleanup_temp(video_id)

            self._update_progress(video_record, "done", 0, progress_callback)
            return video_record

        except PipelineCancelledError:
            video_record.status = VideoStatus.CANCELLED.value
            video_record.cancelled_at = datetime.now(timezone.utc)
            story.status = StoryStatus.VIDEO_CANCELLED.value
            self.db.commit()
            cleanup_temp(video_id)
            raise

        except PipelinePausedError:
            video_record.status = VideoStatus.PAUSED.value
            video_record.is_paused = True
            video_record.paused_at = datetime.now(timezone.utc)
            story.status = StoryStatus.VIDEO_PAUSED.value
            self.db.commit()
            raise

        except (TTSProviderError, FFmpegComposerError, OSError) as exc:
            self._record_error(video_record, exc, video_record.current_step)
            story.status = StoryStatus.VIDEO_FAILED.value
            self.db.commit()
            raise VideoPipelineError(f"Video generation failed at {video_record.current_step}: {exc}")

        except Exception as exc:
            self._record_error(video_record, exc, video_record.current_step)
            story.status = StoryStatus.VIDEO_FAILED.value
            self.db.commit()
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