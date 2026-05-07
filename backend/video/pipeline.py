"""End-to-end video generation pipeline."""

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, List

from sqlalchemy.orm import Session

from backend.models import Story, GeneratedVideo, StoryStatus, VideoStatus
from backend.reddit.linker import UpdateLinker
from backend.video.tts import TTSEngine, TTSProviderError
from backend.video.subtitles import SubtitleGenerator
from backend.video.composer import FFmpegComposer, FFmpegComposerError
from backend.video.thumbnail import ThumbnailGenerator
from backend.video.utils import (
    get_output_folder,
    get_temp_folder,
    cleanup_temp,
    select_background_video,
    get_video_info,
)
from backend.schemas import SubtitleStyle


class VideoPipelineError(Exception):
    pass


class VideoPipeline:
    def __init__(self, db: Session, ffmpeg_path: str = "ffmpeg"):
        self.db = db
        self.ffmpeg_path = ffmpeg_path
        self.composer = FFmpegComposer(ffmpeg_path)
        self.subtitle_gen = SubtitleGenerator(model_size="base")
        self.thumbnail_gen = ThumbnailGenerator()

    def _update_progress(
        self,
        video_record: GeneratedVideo,
        percent: int,
        step: str,
        callback: Optional[Callable[[int, str], None]] = None,
    ) -> None:
        video_record.progress_percent = percent
        self.db.commit()
        if callback:
            callback(percent, step)

    def _build_narrative_text(self, story: Story, include_updates: bool) -> str:
        parts = [f"{story.title}. {story.body or ''}"]

        if include_updates and story.updates:
            linker = UpdateLinker(self.db)
            chain = linker.get_story_chain(story.id)
            for update in chain[1:]:
                parts.append(f"Update. {update.title}. {update.body or ''}")

        return "\n\n".join(parts)

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
            word = re.sub(r'[^\w]', '', word)
            if len(word) > 3 and word not in stop_words:
                freq[word] = freq.get(word, 0) + 1

        top = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:5]
        hashtags = [f"#{word}" for word, _ in top]
        hashtags.extend(["#Reddit", "#StoryTime", "#RedditStories"])

        return hashtags[:8]

    def generate(
        self,
        story_id: int,
        include_updates: bool = True,
        tts_provider: str = "openai",
        tts_voice: str = "alloy",
        background_source: str = "",
        video_format: str = "shorts",
        subtitle_style: Optional[SubtitleStyle] = None,
        generate_hashtags: bool = True,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> GeneratedVideo:
        story = self.db.query(Story).filter(Story.id == story_id).first()
        if not story:
            raise VideoPipelineError(f"Story {story_id} not found")

        if story.generated_video:
            raise VideoPipelineError(f"Video already exists for story {story_id}")

        output_folder = get_output_folder(story.title)
        temp_folder = get_temp_folder(story_id)

        video = GeneratedVideo(
            story_id=story_id,
            video_path=str(output_folder / "video.mp4"),
            thumbnail_path=str(output_folder / "thumbnail.jpg"),
            format=video_format,
            tts_voice=tts_voice,
            tts_provider=tts_provider,
            background_source=background_source,
            subtitle_style=subtitle_style.model_dump() if subtitle_style else {},
            status=VideoStatus.PROCESSING.value,
            progress_percent=0,
        )
        self.db.add(video)
        self.db.commit()
        self.db.refresh(video)

        try:
            self._update_progress(video, 5, "preparing narrative", progress_callback)
            narrative = self._build_narrative_text(story, include_updates)

            hashtags = []
            if generate_hashtags:
                hashtags = self._generate_hashtags(narrative)
                video.subtitle_style = {**(video.subtitle_style or {}), "hashtags": hashtags}

            self._update_progress(video, 10, "generating speech", progress_callback)
            tts_engine = TTSEngine(self.db)
            audio_path = temp_folder / "narration.mp3"
            audio_duration = tts_engine.synthesize(
                narrative, tts_provider, tts_voice, audio_path
            )
            video.audio_path = str(audio_path)

            self._update_progress(video, 30, "transcribing audio", progress_callback)
            whisper_result = self.subtitle_gen.transcribe(str(audio_path))

            self._update_progress(video, 45, "generating subtitles", progress_callback)
            subtitle_path = temp_folder / "subtitles.ass"
            dims = {"shorts": (1080, 1920), "normal": (1920, 1080)}
            w, h = dims.get(video_format, (1080, 1920))
            self.subtitle_gen.generate_ass(
                whisper_result,
                subtitle_path,
                subtitle_style or SubtitleStyle(),
                video_width=w,
                video_height=h,
            )
            video.subtitle_path = str(subtitle_path)

            self._update_progress(video, 55, "selecting background", progress_callback)
            bg_video = select_background_video(background_source)

            self._update_progress(video, 60, "compositing video", progress_callback)

            def ff_callback(percent, step):
                mapped = 60 + int(percent * 0.3)
                self._update_progress(video, mapped, step, progress_callback)

            final_duration = self.composer.compose(
                bg_video,
                str(audio_path),
                str(subtitle_path) if Path(subtitle_path).exists() else None,
                str(output_folder / "video.mp4"),
                video_format=video_format,
                progress_callback=ff_callback,
            )
            video.duration_seconds = final_duration

            self._update_progress(video, 92, "generating thumbnail", progress_callback)
            self.thumbnail_gen.generate(
                story.title,
                story.subreddit,
                Path(video.thumbnail_path),
                score=story.score,
            )

            video.status = VideoStatus.DONE.value
            video.progress_percent = 100
            video.completed_at = datetime.now(timezone.utc)

            story.status = StoryStatus.VIDEO_DONE.value

            video.file_size_bytes = Path(video.video_path).stat().st_size

            self.db.commit()

            cleanup_temp(story_id)

            self._update_progress(video, 100, "complete", progress_callback)
            return video

        except Exception as exc:
            video.status = VideoStatus.FAILED.value
            video.error_message = str(exc)
            video.progress_percent = 0
            story.status = StoryStatus.VIDEO_FAILED.value
            self.db.commit()
            cleanup_temp(story_id)
            raise VideoPipelineError(f"Video generation failed: {exc}")

    def get_progress(self, video_id: int) -> dict:
        video = self.db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
        if not video:
            raise VideoPipelineError(f"Video {video_id} not found")

        return {
            "video_id": video.id,
            "status": video.status,
            "progress_percent": video.progress_percent,
            "current_step": self._get_step_name(video.progress_percent),
            "error_message": video.error_message,
        }

    def _get_step_name(self, percent: int) -> str:
        if percent == 0:
            return "waiting"
        elif percent <= 10:
            return "preparing"
        elif percent <= 30:
            return "text-to-speech"
        elif percent <= 55:
            return "subtitle generation"
        elif percent <= 90:
            return "video compositing"
        elif percent <= 99:
            return "finalizing"
        return "complete"
