from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional, List

from sqlalchemy import String, Text, Integer, DateTime, Boolean, ForeignKey, JSON, Float
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class StoryStatus(str, PyEnum):
    FETCHED = "fetched"
    STORED = "stored"
    UPDATE_LINKED = "update_linked"
    READY_FOR_VIDEO = "ready_for_video"
    VIDEO_PROCESSING = "video_processing"
    VIDEO_DONE = "video_done"
    VIDEO_FAILED = "video_failed"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    UPLOAD_FAILED = "upload_failed"


class VideoStatus(str, PyEnum):
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(primary_key=True)
    reddit_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(100), index=True)
    subreddit: Mapped[str] = mapped_column(String(100), index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text)
    permalink: Mapped[str] = mapped_column(Text)
    created_utc: Mapped[datetime] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    status: Mapped[str] = mapped_column(
        String(50), default=StoryStatus.STORED.value
    )

    parent_story_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("stories.id"), nullable=True, index=True
    )
    is_update: Mapped[bool] = mapped_column(Boolean, default=False)
    update_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    updates: Mapped[List["Story"]] = relationship(
        back_populates="parent_story",
        cascade="all, delete-orphan",
    )
    parent_story: Mapped[Optional["Story"]] = relationship(
        back_populates="updates",
        remote_side="Story.id",
    )

    generated_video: Mapped[Optional["GeneratedVideo"]] = relationship(
        back_populates="story",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<Story(id={self.id}, reddit_id={self.reddit_id}, title={self.title[:50]}...)>"


class Subreddit(Base):
    __tablename__ = "subreddits"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    added_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    fetch_settings: Mapped[dict] = mapped_column(JSON, default=dict)

    def __repr__(self) -> str:
        return f"<Subreddit(name={self.name})>"


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


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

    story: Mapped["Story"] = relationship(back_populates="generated_video")

    def __repr__(self) -> str:
        return f"<GeneratedVideo(id={self.id}, story_id={self.story_id}, status={self.status})>"


class Notification(Base):
    """Real-time notification queue for the UI."""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(50), index=True)
    level: Mapped[str] = mapped_column(String(20), default="info")
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, type={self.type}, level={self.level})>"
