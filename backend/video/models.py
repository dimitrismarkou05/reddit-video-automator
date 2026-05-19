from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional, Dict, Any
from sqlalchemy import String, Text, Integer, DateTime, Boolean, ForeignKey, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base


class VideoStatus(str, PyEnum):
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class GeneratedVideo(Base):
    __tablename__ = "generated_videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), unique=True)

    video_path: Mapped[str] = mapped_column(Text)
    thumbnail_path: Mapped[str] = mapped_column(Text)
    audio_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subtitle_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    format: Mapped[str] = mapped_column(String(20), default="shorts")
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(50), default=VideoStatus.PROCESSING.value)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)

    tts_voice: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tts_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    background_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subtitle_style: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    youtube_video_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    youtube_upload_status: Mapped[str] = mapped_column(String(50), default="not_uploaded")
    youtube_analytics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

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
