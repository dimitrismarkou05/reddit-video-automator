from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional, Dict, Any
from sqlalchemy import String, Text, Integer, DateTime, Boolean, ForeignKey, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base


class VideoStatus(str, PyEnum):
    QUEUED = "queued"
    TTS_DONE = "tts_done"
    TRANSCRIBE_DONE = "transcribe_done"
    SUBTITLES_DONE = "subtitles_done"
    COMPOSITING_DONE = "compositing_done"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class GeneratedVideo(Base):
    __tablename__ = "generated_videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), unique=True)

    # FIX 1: Made nullable since paths are set during pipeline execution, not at creation
    video_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audio_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subtitle_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    format: Mapped[str] = mapped_column(String(20), default="shorts")
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(50), default=VideoStatus.QUEUED.value)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)

    current_step: Mapped[str] = mapped_column(String(50), default="queued")
    step_progress: Mapped[int] = mapped_column(Integer, default=0)
    status_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    temp_files_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    error_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_step: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    queue_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    tts_audio_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    whisper_result_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    subtitle_ass_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    selected_background_video: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    background_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subtitle_style: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # FIX 1: Store generation parameters for retry/resume
    voice_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    include_updates: Mapped[bool] = mapped_column(Boolean, default=True)
    generate_hashtags: Mapped[bool] = mapped_column(Boolean, default=True)

    youtube_video_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    youtube_upload_status: Mapped[str] = mapped_column(String(50), default="not_uploaded")
    youtube_analytics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    queued_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_progress_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    story: Mapped["Story"] = relationship(
        "Story",
        back_populates="generated_video",
    )

    def __repr__(self) -> str:
        return f"<GeneratedVideo(id={self.id}, story_id={self.story_id}, status={self.status})>"
